"""Verifier: checks a commentary line against the facts it was allowed to use.

Deterministic, no model. A line is rejected when it contains
  - a number the facts do not support (a made-up xG, minute, speed, percentage),
  - a scoreline that is not the real one,
  - a player who is not part of the moment,
  - a tactical claim (high line, low block, pressing, in behind, a switch, between the lines, a counter) the moment's facts do not carry (7.5),
  - a trait word (pace, aerial threat, ...) in a sentence that names no player who has the trait,
  - a habit (keeps winning it, always short, never across) the moment's facts do not carry (a pattern_insight or its pay-off),
  - a number written as a word ("eleven times", "elfmal", "onze fois") the facts do not support, for a model line (`spelled`),
  - a win in a season record of comebacks ("won three times", "逆転勝ち"): the record counts points after being behind, draws included,
  - a count of anything in a beginner line ("three passes", "drei Pässe", "trois passes"), for a model line (`style`),
  - the wrong language,
  - an em dash or a middle dot ("·", "・") in a model line (`spelled`): the user's rule for every text a viewer sees,
  - more words than the time slot allows,
  - in a live run that joined a running match (`match_so_far`): an earlier scorer or goal minute outside a goal, analysis, score or
    scene-setting line, a goal minute next to a scorer who did not score in it, a later goal called the opener, "goalless" after goals.
The world languages (es, it, pt, nl, tr, ja) have the same rules: their own stop words, number words, count nouns, claims and traits. Japanese is
written without spaces: its language check reads the script (kana), names are matched without word boundaries, and a name in katakana
(イブセン) is mapped to the roster by its consonant skeleton (`skeleton`, `kana_skeleton`), so a katakana name counts as that player.
Rejection reasons go back to the agent that wrote the line, which gets a retry.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from ..schema import MatchMeta
from .lang import LANGS, est_seconds
from .moments import Moment, render_params, surname
from .templates import NAME_KEYS

NUM_RE = re.compile(r"(?<![\w.])\d+(?:[.,]\d+)?")
SCORE_RE = re.compile(r"(?<!\d)(\d{1,2})\s*[-–:対]\s*(\d{1,2})(?!\d)")  # 対: Japanese writes 1対1
WORD_RE = re.compile(r"(?:[^\W\d_]|')+")  # letters of any script (ñ, ı, ş, ã ...); Japanese runs are one "word" each and are read by script instead
KANA_RE = re.compile(r"[\u3040-\u30ff]")  # hiragana and katakana: only Japanese writes them
KATAKANA_RUN = re.compile(r"[\u30a1-\u30fa\u30fc]+")  # a katakana word (the middle dot U+30FB splits names)
FORBIDDEN_PUNCT = re.compile(r"[\u2014\u00b7\u30fb\u2027\u2219]")  # em dash, middle dot, katakana middle dot, hyphenation point, bullet operator

STOPWORDS = {
    "en": {"the", "and", "is", "are", "to", "of", "a", "in", "for", "with", "it", "that", "on", "they", "have", "has"},
    "de": {"der", "die", "das", "und", "ist", "mit", "den", "ein", "eine", "nicht", "auf", "für", "von", "im", "hat", "sie"},
    "fr": {"le", "la", "les", "et", "est", "un", "une", "des", "du", "de", "pour", "avec", "que", "dans", "ce", "sur", "a", "cette", "au", "aux", "en"},  # "a" is English too; a French sentence of two perfects ("a réussi ... a disputé") was read as English
    # the world languages: function words, the most frequent first; shared ones ("de", "la", "que", "e") count for every language that has them
    "es": {"el", "los", "las", "y", "del", "con", "por", "una", "es", "lo", "se", "pero", "esta", "está", "al", "su", "muy", "ya", "hay", "otra", "vez", "como", "la", "que", "de", "en", "un", "para", "no", "más", "ahora"},
    "it": {"il", "gli", "della", "dello", "nel", "nella", "è", "di", "che", "per", "non", "ma", "ed", "e", "un", "una", "alla", "al", "questa", "volta", "sempre", "ancora", "poi", "la", "lo", "con"},
    "pt": {"o", "os", "as", "e", "do", "da", "dos", "das", "não", "um", "uma", "com", "para", "que", "no", "na", "é", "mas", "ao", "pra", "essa", "dessa", "vez", "sempre", "de", "em"},
    "nl": {"de", "het", "een", "en", "van", "is", "niet", "op", "met", "voor", "maar", "naar", "die", "dat", "nu", "weer", "er", "hij", "zijn", "deze", "keer", "altijd", "nooit", "ze", "wel"},
    "tr": {"ve", "bir", "bu", "da", "de", "ile", "için", "çok", "ama", "şimdi", "yine", "hiç", "her", "kez", "sonra", "hep", "bile", "daha", "artık", "işte", "ki", "mi", "gibi"},
}


# ---- the claims lexicon (docs/DATA-MODEL.md 7.5). Tactical words are allowed only when the moment's facts carry the claim; trait words
# only in a sentence that names a player who has the trait (the roster in meta.json is the fact). The patterns are deliberately narrow:
# an everyday use of a word ("at pace", "deep in their half", "the switch of play" in a build-up) must not be rejected, so only the
# phrases a colour analyst uses for the tactical idea are listed. ----
CLAIMS: dict[str, dict[str, str]] = {
    "high_line": {
        "en": r"high line|(?:pushed|pushing|push|moved|moving) (?:the|their) (?:back )?line (?:right |well )?up|defend(?:s|ing)? high|high block",
        "de": r"hohe(?:n)? (?:Abwehr)?[kK]ette|Abwehrkette weit nach vorn|hoch im Feld|verteidigt hoch|hohe(?:n)? Block",
        "fr": r"ligne haute|relev\w* sa ligne|défend(?:ent)? (?:très )?haut|bloc haut",
    },
    "press_high": {
        "en": r"press(?:es|ing|ed)? high|high press|pressing in numbers|in numbers",
        "de": r"press(?:t|en|ing) hoch|hohes Pressing|mit vielen Leuten|läuft früh an",
        "fr": r"press(?:e|ent|ing) haut|pressing haut|à plusieurs",
    },
    "press_passive": {
        "en": r"happy to let the ball go|not pressing|sit(?:s|ting)? off|passive press",
        "de": r"presst kaum|lässt den Gegner kommen|passives Pressing",
        "fr": r"laisse(?:nt)? volontiers le ballon|ne presse(?:nt)? pas|pressing passif",
    },
    "low_block": {
        "en": r"low block|sit(?:s|ting)? deep|dropped deep|drop(?:s|ping)? deep|defend(?:s|ing)? deep|deep block|retreat(?:s|ed|ing)? deep",
        "de": r"tiefe(?:n)? Block|steht tief|zieht sich tief|tief zurück|verteidigt tief",
        "fr": r"bloc bas|attend bas|replié|défend(?:ent)? bas",
    },
    "in_behind": {
        "en": r"in behind|beyond the (?:back )?line|runs? in behind",
        "de": r"in den Rücken|hinter die Kette|hinter die Abwehr",
        "fr": r"dans le dos de la défense|derrière la défense",
    },
    "switch": {
        "en": r"\bswitch(?:es|ed|ing)?\b|switch of play",
        "de": r"Seitenwechsel|verlagert|verlagert das Spiel|Verlagerung",
        "fr": r"renvers\w+|changement d'aile|transversale",
    },
    "line_break": {
        "en": r"between the lines|splits? the lines|break(?:s|ing)? the lines|line-breaking",
        "de": r"zwischen den Linien|durchbricht die Linie|überspielt die Linie",
        "fr": r"entre les lignes|casse les lignes|brise la ligne",
    },
    "tempo_slow": {
        "en": r"slow(?:ing|s)? (?:the game|it) (?:right )?down|in no hurry|tak(?:e|es|ing) their time|slow and patient",
        "de": r"nimmt das Tempo|Tempo raus|lässt sich Zeit|ruhig und geduldig",
        "fr": r"ralenti\w*|prend(?:ent)? son temps|prend(?:ent)? leur temps|calmement et patiemment",
    },
    "tempo_high": {
        "en": r"real tempo|high tempo|quick tempo|at tempo|ball quickly",
        "de": r"mit (?:richtig )?Tempo|hohem Tempo|hohes Tempo|schnell laufen",
        "fr": r"vrai rythme|rythme (?:élevé|soutenu)|circuler vite",
    },
    # habits (commentary/patterns.py): only a pattern_insight, or a goal analysis that pays one off, carries them
    "habit_winner": {
        "en": r"keeps? winning (?:it|the ball)|winning it (?:back )?again and again|keeps getting (?:it|the ball) back",
        "de": r"holt (?:die|jeden|alle) B[aä]ll\w*|holt (?:ihn|den Ball) schon wieder|gewinnt (?:jeden|alle) B[aä]ll\w*",
        "fr": r"ballon sur ballon|récupère (?:tous les|chaque) ballons?|récupère encore et encore",
    },
    "habit_short": {
        "en": r"(?:always|every time|each time)[^.!?]{0,30}\bshort\b|\bshort\b[^.!?]{0,12}\b(?:every time|each time|always)\b|(?:then|and) it goes short",
        "de": r"immer (?:nur )?kurz|jedes Mal kurz|kurz, jedes Mal",
        "fr": r"toujours court|à chaque fois court|systématiquement court",
    },
    "habit_never_across": {
        "en": r"never across|not once across|nothing across|nobody (?:plays|puts|gets) it across|not (?:one|a single) (?:switch|ball across)|no switch",
        "de": r"nie(?:mals)? rüber|nie quer|keine Verlagerung|nicht eine Verlagerung|wo ist die Verlagerung|nie verlagert",
        "fr": r"jamais de l'autre côté|pas une (?:seule )?transversale|aucune transversale|jamais (?:la |une |de )?transversale|jamais renvers\w*",
    },
    "counter": {
        "en": r"counter-?attack|on the break|break(?:s|ing)? at speed|\bcounters?\b",
        "de": r"Konter|Umschaltspiel",
        "fr": r"contre-attaque|en contre|jaillir en contre",
    },
}
TRAIT_WORDS: dict[str, dict[str, str]] = {  # trait code (schema.Trait) -> pattern per language
    "rapid": {"en": r"real pace|blistering pace|\bpacy\b|\brapid\b|great pace", "de": r"enormes Tempo|blitzschnell", "fr": r"vraie vitesse|vitesse folle"},
    "quick_off_the_mark": {"en": r"quick off the mark|sharp first step", "de": r"sofort auf Touren", "fr": r"démarre très vite"},
    "aerial_threat": {"en": r"dominant in the air|aerial threat|strong in the air", "de": r"stark in der Luft|Kopfballstark|Kopfballungeheuer", "fr": r"dominant dans les airs|redoutable de la tête"},
    "long_range": {"en": r"from distance|long-range|from range", "de": r"aus der Distanz|Fernschuss|Fernschütze", "fr": r"de loin|frappe de loin"},
    "set_piece_taker": {"en": r"dead-ball specialist|set[- ]piece specialist|set[- ]piece taker", "de": r"Standardspezialist", "fr": r"spécialiste des coups de pied arrêtés|coups de pied arrêtés"},
    "press_resistant": {"en": r"calm under pressure|so calm under pressure|press-resistant", "de": r"unter Druck ganz ruhig|druckresistent", "fr": r"calme sous la pression|très calme sous la pression"},
    "engine": {"en": r"never stops running|the engine", "de": r"läuft unermüdlich|Motor", "fr": r"ne s'arrête jamais de courir|le moteur"},
    "two_footed": {"en": r"either foot|both feet|two-footed", "de": r"beiden Füßen|beidfüßig", "fr": r"des deux pieds|ambidextre"},
    "tough_tackler": {"en": r"tough tackler|hard tackler|combative", "de": r"harter Zweikämpfer|zweikampfstark", "fr": r"défenseur teigneux|teigneux"},
    "visionary": {"en": r"sees the pass early|visionary|great vision", "de": r"erkennt den Pass früh|Spielübersicht", "fr": r"voit la passe très tôt|grande vision"},
    "dribbler": {"en": r"take a man on|loves to dribble|dribbler", "de": r"ins Dribbling|Dribbler", "fr": r"éliminer son vis-à-vis|dribbleur"},
}
CLAIMS_WORLD: dict[str, dict[str, str]] = {'high_line': {'es': 'línea (?:muy )?adelantada|defensa adelantada|bloque alto', 'it': 'linea alta|difesa alta|blocco alto', 'pt': 'linha alta|defesa adiantada|bloco alto', 'nl': 'hoge (?:verdedigings)?lijn|hoog blok|verdedigt hoog', 'tr': 'önde savunma|yüksek savunma hattı|yüksek blok', 'ja': '高いライン|ハイライン|最終ラインを高く'}, 'press_high': {'es': 'presión alta|presiona(?:n)? arriba', 'it': 'pressing alto|press(?:a|ano) alto', 'pt': 'pressão alta|marcação alta|pressiona(?:m)? alto', 'nl': 'hoog druk|zet(?:ten)? hoog druk|hoge druk', 'tr': 'önde baskı|yüksek pres', 'ja': 'ハイプレス|前からプレス|前からのプレス|高い位置からプレス'}, 'press_passive': {'es': 'no presiona(?:n)?|presión pasiva', 'it': 'non press(?:a|ano)|pressing passivo', 'pt': 'não pressiona(?:m)?|pressão passiva', 'nl': 'zet(?:ten)? geen druk|passieve druk', 'tr': 'baskı yapmıyor|pasif baskı', 'ja': 'プレスをかけない|プレスがない'}, 'low_block': {'es': 'bloque bajo|repliegue|defiende(?:n)? (?:muy )?atrás|encerrad[oa]s? atrás', 'it': 'blocco basso|difesa bassa|si chiud(?:e|ono) dietro|chiusi dietro', 'pt': 'bloco baixo|retrancad\\w+|recuad\\w+ demais', 'nl': 'laag blok|zakt (?:diep )?in|staat diep|ingezakt', 'tr': 'alçak blok|geride kapan\\w+|geride bekliyor', 'ja': '低いブロック|引いて守|ベタ引き|自陣に引'}, 'in_behind': {'es': 'a la espalda de la defensa|al espacio a la espalda', 'it': 'alle spalle della difesa|dietro la difesa', 'pt': 'nas costas da (?:defesa|zaga)', 'nl': 'achter de verdediging|in de rug van de verdediging', 'tr': 'savunmanın arkasına|arkaya sarkan', 'ja': '裏へ|裏を取|ラインの裏'}, 'switch': {'es': 'cambio de (?:orientación|juego|frente)', 'it': 'cambio (?:di gioco|di campo|di fronte)', 'pt': 'inversão|virada de jogo|vir(?:a|ou|ar) o jogo', 'nl': '\\bswitch\\b|wissel van kant|crossverplaatsing|verplaatst het spel', 'tr': 'oyunun yönünü değiştir\\w*|çapraz pas|kanat değiştir\\w*', 'ja': 'サイドチェンジ|逆サイドへの展開'}, 'line_break': {'es': 'entre líneas|rompe(?:n)? líneas', 'it': 'tra le linee|romp(?:e|ono) le linee', 'pt': 'entrelinhas|entre as linhas|quebra(?:r)? as linhas', 'nl': 'tussen de linies|door de linies', 'tr': 'hatlar arasında|çizgiler arasında|hatları kır\\w*', 'ja': 'ライン間|ラインを破'}, 'tempo_slow': {'es': 'baja(?:n)? el ritmo|sin prisa|se toma(?:n)? su tiempo', 'it': 'abbass(?:a|ano) i ritmi|senza fretta', 'pt': 'sem pressa|diminu\\w+ o ritmo|cadencia(?:m)? o jogo', 'nl': 'haalt het tempo eruit|geen haast', 'tr': 'oyunu yavaşlat\\w*|acele etmeden|ritmi düşür\\w*', 'ja': 'テンポを落と|ゆっくり回'}, 'tempo_high': {'es': 'ritmo alto|mucho ritmo', 'it': 'ritmo alto|ritmi alti', 'pt': 'ritmo alto|ritmo forte', 'nl': 'hoog tempo|tempo erin', 'tr': 'yüksek tempo|tempolu', 'ja': 'ハイテンポ|テンポを上げ|速いテンポ'}, 'habit_winner': {'es': '(?:recupera|gana|roba) (?:todos los|cada) balon\\w*|recupera una y otra vez|no para de recuperar|sigue recuperando|las recupera todas', 'it': "recupera (?:tutti i|ogni) pallon\\w*|continua a recuperare|recupera palloni su palloni|recupera un pallone dopo l'altro", 'pt': '(?:recupera|rouba|ganha) todas as bolas|recupera bola atrás de bola|não para de recuperar|continua recuperando', 'nl': 'wint (?:elke|alle|steeds de|steeds) ba(?:l|llen)|blijft (?:de bal |ballen )?(?:winnen|veroveren)|pakt (?:elke|alle|steeds) ba(?:l|llen)', 'tr': 'her topu kazan\\w*|sürekli top kazan\\w*|topları kazanıyor|topu (?:hep|sürekli) kazan\\w*', 'ja': '(?:何度も|次々と|ことごとく)(?:ボールを)?(?:奪|回収)|ボールを奪い続け'}, 'habit_short': {'es': 'siempre (?:en )?corto|cada vez,? (?:en )?corto|corto,? siempre', 'it': 'sempre (?:il passaggio )?cort[oa]|ogni volta cort[oa]', 'pt': 'sempre (?:o passe )?curto|toda vez curto|é sempre curto', 'nl': 'altijd kort|steeds kort|elke keer kort', 'tr': 'hep kısa|her seferinde kısa|sürekli kısa', 'ja': '(?:いつも|毎回|必ず)(?:短い|ショート)'}, 'habit_never_across': {'es': 'nunca (?:al otro lado|cruza|de banda a banda|el cambio)|ni un (?:solo )?cambio|ningún cambio', 'it': "mai (?:dall'altra parte|il cambio|sull'altro lato)|nessun cambio|neanche un cambio", 'pt': 'nunca (?:pro|para o) outro lado|nenhuma inversão|nunca a inversão|nem uma inversão', 'nl': 'nooit (?:naar de )?andere kant|nooit over|geen enkele switch|nooit een switch', 'tr': '(?:asla|hiç|bir kez bile) (?:diğer|öbür) (?:tarafa|kanada)|hiç çevirmiyor|bir kez bile çevir\\w*', 'ja': '(?:一度も|全く)(?:逆サイド|サイドチェンジ|反対側)|(?:逆サイド|反対側)へは一度も|サイドチェンジ(?:が|は)(?:ない|ありません)'}, 'counter': {'es': 'contraataque|contragolpe', 'it': 'contropiede|ripartenza', 'pt': 'contra-ataque|contragolpe', 'nl': '\\bcounter\\b|uitbraak', 'tr': 'kontra(?: atak)?', 'ja': 'カウンター'}}
TRAIT_WORDS_WORLD: dict[str, dict[str, str]] = {'rapid': {'es': 'muy rápido|rapidísimo|velocidad endiablada', 'it': 'velocissimo|rapidissimo', 'pt': 'muito rápido|rapidíssimo', 'nl': 'razendsnel|bloedsnel', 'tr': 'çok hızlı|müthiş hızlı', 'ja': '俊足|快足'}, 'quick_off_the_mark': {'es': 'arranque explosivo', 'it': 'scatto bruciante', 'pt': 'arranque explosivo', 'nl': 'explosieve start', 'tr': 'patlayıcı çıkış', 'ja': '初速が速い'}, 'aerial_threat': {'es': 'fuerte por arriba|domina el juego aéreo', 'it': 'forte di testa|dominante nel gioco aereo', 'pt': 'forte no jogo aéreo|bom de cabeça', 'nl': 'sterk in de lucht|kopsterk', 'tr': 'hava toplarında güçlü', 'ja': '空中戦に強い|ヘディングが強い'}, 'long_range': {'es': 'desde lejos|de lejos|disparo lejano', 'it': 'da lontano|dalla distanza', 'pt': 'de longe', 'nl': 'van afstand|afstandsschot', 'tr': 'uzaktan', 'ja': '遠目から|ロングシュートが得意|ミドルが得意'}, 'set_piece_taker': {'es': 'especialista (?:a|en) balón parado', 'it': 'specialista dei calci piazzati', 'pt': 'especialista em bola parada', 'nl': 'spelhervattingsspecialist', 'tr': 'duran top uzmanı', 'ja': 'セットプレーの名手|プレースキッカー'}, 'press_resistant': {'es': 'tranquilo bajo presión', 'it': 'calmo sotto pressione', 'pt': 'calmo sob pressão', 'nl': 'rustig onder druk', 'tr': 'baskı altında sakin', 'ja': 'プレッシャーに強い'}, 'engine': {'es': 'no para de correr|pulmón', 'it': 'non smette mai di correre|polmone', 'pt': 'não para de correr|pulmão', 'nl': 'onvermoeibaar', 'tr': 'durmadan koşuyor|yorulmak bilmiyor', 'ja': '運動量が豊富|走り続ける'}, 'two_footed': {'es': 'con las dos piernas|ambidiestro', 'it': 'con entrambi i piedi|ambidestro', 'pt': 'com as duas pernas|ambidestro', 'nl': 'tweebenig|met beide benen', 'tr': 'iki ayağını da|iki ayaklı', 'ja': '両足'}, 'tough_tackler': {'es': 'duro en el cruce|aguerrido', 'it': 'mastino|duro nei contrasti', 'pt': 'marcador duro|viril', 'nl': 'harde tackler|keiharde verdediger', 'tr': 'sert müdahale|sert savunmacı', 'ja': '対人に強い|ハードタックル'}, 'visionary': {'es': 'gran visión|ve el pase antes', 'it': 'grande visione|vede il passaggio prima', 'pt': 'grande visão|enxerga o passe', 'nl': 'groot overzicht|ziet de pass vroeg', 'tr': 'oyun görüşü|pası erken görüyor', 'ja': '視野が広い'}, 'dribbler': {'es': 'regateador|encarar', 'it': "dribblatore|saltare l'uomo", 'pt': 'driblador|partir para cima', 'nl': 'dribbelaar|zijn man uitspelen', 'tr': 'çalımcı|adam eksilt\\w*', 'ja': 'ドリブラー|仕掛ける'}}
for _c, _langs in CLAIMS_WORLD.items():  # one lexicon: the world phrases sit next to en, de and fr
    CLAIMS[_c].update(_langs)
for _c, _langs in TRAIT_WORDS_WORLD.items():
    TRAIT_WORDS[_c].update(_langs)
_CLAIM_RX = {c: {lang: re.compile(p, re.I) for lang, p in langs.items()} for c, langs in CLAIMS.items()}
# Claims a moment's facts rule out (Allowed.forbid). The comebacks story (sim/dossier.py) counts matches in which the team took points after
# being behind: a draw counts, so "won", "turned it round" or 逆転勝ち overstate it.
FORBIDDEN_CLAIMS: dict[str, dict[str, str]] = {
    "comeback_win": {
        "en": r"\bwon\b|\bwins?\b|victor(?:y|ies)|turned (?:it|games|matches) (?:a)?round",
        "de": r"gewonnen|\bSiege?\b|gedreht",
        "fr": r"gagn\w+|victoires?|renvers\w+",
        "es": r"ganad\w*|\bgan[óa]\b|victorias?|le dio la vuelta",
        "it": r"\bvint\w*|vittori\w+|ribaltat\w*",
        "pt": r"\bvenc\w+|vitórias?|\bvir(?:ou|aram|ar|ada|adas)\b",
        "nl": r"gewonnen|\bwon\b|zeges?\b|overwinning\w*",
        "tr": r"kazan\w*|galibiyet\w*",
        "ja": r"逆転勝ち|勝利|勝っ|勝ち(?!点)",
    },
}
_FORBID_RX = {c: {lang: re.compile(p, re.I) for lang, p in langs.items()} for c, langs in FORBIDDEN_CLAIMS.items()}
# Live runs that join a running match (Allowed.prior_goals): once a goal has gone in, no later goal is "the opener" and the match is not
# goalless. An opener phrase is still true of the real first goal, so it passes in a sentence that names that goal's scorer or team.
OPENER: dict[str, str] = {
    "en": r"\bopener\b|opening goal|open(?:s|ed)? the scoring|first goal of (?:the|this) (?:match|game|day|night|afternoon|evening)",
    "de": r"erste[nrs]? (?:Tor|Treffer) (?:des|dieses) (?:Spiel|Abend|Nachmittag|Tag)\w*|Torreigen|Dosenöffner",
    "fr": r"premier but (?:du|de ce|de la) (?:match|rencontre|soirée|journée)|ouvr\w+ (?:le|la) (?:score|marque)|ouverture du score",
    "es": r"primer gol del (?:partido|encuentro)|abr\w+ el marcador|abr\w+ la lata",
    "it": r"primo gol (?:della partita|del match|dell'incontro)|sblocc\w+ (?:il risultato|la partita)|apr\w+ le marcature",
    "pt": r"primeiro gol (?:da partida|do jogo)|abr\w+ o placar|inaugur\w+ o marcador",
    "nl": r"eerste (?:doelpunt|goal) van de (?:wedstrijd|middag|avond)|opent de score|opende de score|openingsgoal|openingstreffer",
    "tr": r"maçın ilk gol\w*|skoru açt\w*|skoru açıyor|açılış golü",
    "ja": r"先制|試合最初のゴール|この試合初ゴール",
}
GOALLESS: dict[str, str] = {
    "en": r"goalless|scoreless|nil-nil|level since (?:the )?kick-?off",
    "de": r"torlos|null zu null",
    "fr": r"sans but|score vierge|zéro à zéro",
    "es": r"sin goles|cero a cero|empate a cero",
    "it": r"senza gol|reti inviolate|zero a zero",
    "pt": r"sem gols|zero a zero",
    "nl": r"doelpuntloos|brilstand|nul-nul",
    "tr": r"golsüz",
    "ja": r"スコアレス|無得点|両チーム無得点",
}
_OPENER_RX = {lang: re.compile(p, re.I) for lang, p in OPENER.items()}
_GOALLESS_RX = {lang: re.compile(p, re.I) for lang, p in GOALLESS.items()}
_TRAIT_RX = {c: {lang: re.compile(p, re.I) for lang, p in langs.items()} for c, langs in TRAIT_WORDS.items()}
SENTENCE_RE = re.compile(r"(?<=[.!?])\s+|(?<=[。！？])")  # Japanese ends a sentence with 。！？ and no space

# numbers written as words, two to twenty (one, ein, un are articles and idioms: "one touch", "einer drauf", "en une touche")
NUMBER_WORDS = {
    "en": ["two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen",
           "sixteen", "seventeen", "eighteen", "nineteen", "twenty"],
    "de": ["zwei", "drei", "vier", "fünf", "sechs", "sieben", "acht", "neun", "zehn", "elf", "zwölf", "dreizehn", "vierzehn", "fünfzehn",
           "sechzehn", "siebzehn", "achtzehn", "neunzehn", "zwanzig"],
    "fr": ["deux", "trois", "quatre", "cinq", "six", "sept", "huit", "neuf", "dix", "onze", "douze", "treize", "quatorze", "quinze",
           "seize", "dix-sept", "dix-huit", "dix-neuf", "vingt"],
    "es": ["dos", "tres", "cuatro", "cinco", "seis", "siete", "ocho", "nueve", "diez", "once", "doce", "trece", "catorce", "quince",
           "dieciséis", "diecisiete", "dieciocho", "diecinueve", "veinte"],
    "it": ["due", "tre", "quattro", "cinque", "sei", "sette", "otto", "nove", "dieci", "undici", "dodici", "tredici", "quattordici", "quindici",
           "sedici", "diciassette", "diciotto", "diciannove", "venti"],
    "pt": ["dois", "três", "quatro", "cinco", "seis", "sete", "oito", "nove", "dez", "onze", "doze", "treze", "catorze", "quinze",
           "dezesseis", "dezessete", "dezoito", "dezenove", "vinte"],
    "nl": ["twee", "drie", "vier", "vijf", "zes", "zeven", "acht", "negen", "tien", "elf", "twaalf", "dertien", "veertien", "vijftien",
           "zestien", "zeventien", "achttien", "negentien", "twintig"],
    "tr": ["iki", "üç", "dört", "beş", "altı", "yedi", "sekiz", "dokuz", "on", "on bir", "on iki", "on üç", "on dört", "on beş",
           "on altı", "on yedi", "on sekiz", "on dokuz", "yirmi"],
    "ja": ["二", "三", "四", "五", "六", "七", "八", "九", "十", "十一", "十二", "十三", "十四", "十五", "十六", "十七", "十八", "十九", "二十"],
}
# one, ein, un, uno, um, een, bir, 一 are articles and idioms ("una vez más", "een keer", "bir kez bile", "一度も"), never counted
_EXTRA_WORDS = {"en": {"twice": 2, "thrice": 3}, "de": {}, "fr": {}, "es": {"veintena": 20}, "it": {"ventina": 20}, "pt": {"duas": 2},
                "nl": {"tweemaal": 2, "driemaal": 3}, "tr": {}, "ja": {}}
_JA_COUNTER = r"(?:回|本|度|点|人|つ|分|秒)"  # a kanji numeral is a number only with a counter after it ("三回", "二十分"), else it is part of a word
_NUMWORD_RX = {lang: re.compile(r"(?<![\w-])(" + "|".join(sorted(map(re.escape, [*ws, *(_EXTRA_WORDS[lang] if lang not in LANGS else ())]), key=len, reverse=True)) + r")(?:mal)?(?![\w-])", re.I)
               for lang, ws in NUMBER_WORDS.items() if lang != "ja"}
_NUMWORD_RX["ja"] = re.compile(r"(" + "|".join(sorted(NUMBER_WORDS["ja"], key=len, reverse=True)) + r")(?=" + _JA_COUNTER + r")(?!分[なにだで])")  # 十分な is "enough"
_NUMWORD_VALUE = {lang: {w: i + 2 for i, w in enumerate(ws)} | _EXTRA_WORDS[lang] for lang, ws in NUMBER_WORDS.items()}
_COUNT = {  # a count of things: a number, as digits or a word, then at most one more word, then a countable noun
    "en": r"passes|shots|touches|corners|chances|saves|tackles|crosses|attempts|interceptions|balls|times|goals",
    "de": r"Pässe|Pässen|Schüsse|Schüssen|Torschüsse|Ballkontakte|Kontakte|Ecken|Chancen|Paraden|Flanken|Zweikämpfe|Ballgewinne|Bälle|Tore|Mal",
    "fr": r"passes|tirs|touches|corners|occasions|arrêts|centres|ballons|récupérations|fois|buts",
    "es": r"pases|tiros|disparos|toques|córners|ocasiones|paradas|centros|balones|recuperaciones|veces|goles",
    "it": r"passaggi|tiri|tocchi|calci d'angolo|occasioni|parate|cross|palloni|recuperi|volte|gol",
    "pt": r"passes|chutes|finalizações|toques|escanteios|chances|defesas|cruzamentos|bolas|vezes|gols|desarmes",
    "nl": r"passes|schoten|balcontacten|hoekschoppen|kansen|reddingen|voorzetten|ballen|keer|doelpunten|onderscheppingen",
    "tr": r"pas|şut|vuruş|korner|pozisyon|kurtarış|orta|top|kez|kere|gol",  # Turkish counts in the singular: "üç pas", "üç kez"
}
_COUNT_RX = {lang: re.compile(r"(?<![\w-])(?:\d+|" + "|".join(sorted(map(re.escape, NUMBER_WORDS[lang]), key=len, reverse=True)) + r")\s+(?:\w+\s+)?(?:" + nouns + r")(?!\w)"
                              + (r"|(?<![\w-])(?:" + "|".join(NUMBER_WORDS["de"]) + r")mal(?!\w)" if lang == "de" else "")
                              + (r"|\b(?:twice|thrice)\b" if lang == "en" else ""), re.I)
             for lang, nouns in _COUNT.items()}
_COUNT_RX["ja"] = re.compile(r"(?:\d+|" + "|".join(sorted(NUMBER_WORDS["ja"], key=len, reverse=True)) + r")\s*(?:回|本|度|人|つ)(?!目)")  # 三回, 3本のパス; 3度目 is an ordinal


def _walk(value):
    """Every scalar inside nested params (the facts block of phase 7 nests dicts and lists)."""
    if isinstance(value, dict):
        for k, v in value.items():
            yield k
            yield from _walk(v)
    elif isinstance(value, (list, tuple, set)):
        for v in value:
            yield from _walk(v)
    else:
        yield value


def claims_of(m: Moment) -> set[str]:
    """The tactical claims a moment's facts carry (7.5): its own kind and facet, and the `shape` and `build_up` blocks of an analyst
    moment (DATA-MODEL 7.3), whatever it brings. Nothing else is allowed."""
    p, out = m.params, set()
    facet = p.get("facet")
    if m.kind == "press_on" and facet == "high":
        out.add("press_high")
    elif m.kind == "shape_note":
        out |= {"chase": {"high_line"}, "protect": {"low_block"}}.get(facet, set())
    elif m.kind == "press_note":
        out |= {"intense": {"press_high"}, "passive": {"press_passive"}}.get(facet, set())
    elif m.kind == "phase_note":
        out |= {"high": {"high_line"}, "low": {"low_block"}, "counter": {"counter"}}.get(facet, set())
    elif m.kind == "tempo_note":
        out |= {"slow": {"tempo_slow"}, "high": {"tempo_high"}}.get(re.sub(r"_\d+$", "", facet or ""), set())  # slow_2 and high_2 are the second wording
    elif m.kind == "in_behind":
        out.add("in_behind")
    elif m.kind == "line_break":
        out.add("line_break")
    elif m.kind == "pass_kind" and p.get("pass_type") == "switch":
        out.add("switch")
    for side in (p.get("shape") or {}).values():  # {"home": {"posture", "block", "press", ...}, "away": {...}}
        if not isinstance(side, dict):
            continue
        out |= {"high": {"high_line"}, "low": {"low_block"}}.get(side.get("block"), set())
        out |= {"intense": {"press_high"}, "passive": {"press_passive"}}.get(side.get("press"), set())
        out |= {"chase": {"high_line"}, "protect": {"low_block"}}.get(side.get("posture"), set())
    if m.kind == "pattern_insight" or p.get("pays_off"):  # the habit is the fact; "not one switch" names the switch that never came
        out |= {"habit_winner", "habit_short", "habit_never_across"} if p.get("player") or (p.get("pays_off") or {}).get("ball_winner") else {"habit_short", "habit_never_across"}
        if m.kind == "pattern_insight":
            out.add("switch")
    for step in p.get("move") or ():  # the scoring move of a goal analysis: a step with pass_type switch is a switch in the facts
        if isinstance(step, dict) and step.get("pass_type") == "switch":
            out.add("switch")
    build = p.get("build_up") or {}
    if isinstance(build, dict):
        if "switch" in set(_walk(build.get("chain"))):
            out.add("switch")
        if build.get("line_break"):
            out.add("line_break")
        if build.get("run_in_behind"):
            out.add("in_behind")
    return out


@dataclass
class Violation:
    code: str
    detail: str


@dataclass
class Verdict:
    ok: bool
    violations: list[Violation] = field(default_factory=list)

    def feedback(self) -> str:
        return "; ".join(f"{v.code}: {v.detail}" for v in self.violations)


HISTORY_KINDS = {"shot_goal", "goal_analysis", "momentum", "big_save_analysis", "big_chance_analysis", "score_line", "match_state"}  # may recall the match so far
OWN_GOAL_KINDS = {"shot_goal", "goal_analysis", "score_line"}  # the moment's own goal is the last of the match so far


@dataclass
class Allowed:
    numbers: set[float]
    scores: set[tuple[int, int]]
    names: set[str]  # lower-case surnames and team names the line may mention
    claims: set[str] = field(default_factory=set)  # tactical claims the moment's facts carry (CLAIMS keys, 7.5)
    forbid: set[str] = field(default_factory=set)  # claims the moment's facts rule out (FORBIDDEN_CLAIMS keys)
    goals: list[dict] = field(default_factory=list)  # live: the goals of the match so far a history line may recall (scorer, team, minute)
    prior_goals: int = 0  # live: goals before this moment's own goal (a goal, its analysis, its score line) or before this moment


def _num_set(values) -> set[float]:
    out: set[float] = set()
    for v in values:
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            continue
        out.add(round(float(v), 2))
        out.add(round(float(v), 1))
        if 0 <= v <= 1:
            out.add(float(round(100 * v)))
        out.add(float(round(v)))
    return out


def allowed_for(m: Moment, snapshot: dict, meta: MatchMeta) -> Allowed:
    """Everything a line about moment m may legitimately mention."""
    p = render_params(m, "en")
    raw = dict(m.params)
    nums = _num_set(raw.values()) | _num_set(v for v in p.values() if isinstance(v, (int, float)))
    nums |= {float(int(m.clock.split("+")[0]))}
    scores: set[tuple[int, int]] = set()
    for source in (raw.get("score"), f"{snapshot['score'][0]}-{snapshot['score'][1]}"):
        if source:
            a, b = (int(x) for x in str(source).split("-"))
            scores.add((a, b))
            nums |= {float(a), float(b)}
    if "hg" in raw:
        scores.add((raw["hg"], raw["ag"]))
    st = snapshot["stats"]
    for s in ("H", "A"):
        nums |= _num_set([st[s]["possession"], st[s]["shots"], st[s]["on_target"], st[s]["xg"], st[s]["pass_acc"]])
    wp = snapshot["win"]
    nums |= {float(round(100 * x)) for x in wp}
    names = {meta.teams[s].name.lower() for s in ("H", "A")}
    for key in ("player", "keeper", "receiver", "team", "home", "away", *NAME_KEYS):  # the fast layer may name every player in its params (7.5)
        if key in raw and raw[key]:
            names.add(str(raw[key]).lower())
    names |= {str(n).lower() for n in raw.get("chain") or ()}  # the players of a move
    if isinstance(raw.get("pays_off"), dict) and raw["pays_off"].get("ball_winner"):  # the player of the habit a goal pays off
        names.add(str(raw["pays_off"]["ball_winner"]).lower())
    so_far = snapshot.get("so_far") or {}  # live runs: the match so far (its goals, red cards)
    goals = list(so_far.get("goals") or ())
    history = m.kind in HISTORY_KINDS
    for g in goals:  # every moment may give a score the match has had ("from 0-1 down")
        scores.add(tuple(int(x) for x in str(g["made_it"]).split("-")))
    if history:  # only a goal, an analysis, a score line or the scene-setting line recalls who scored and when (a pass names its own players)
        for g in goals:
            a, b = (int(x) for x in str(g["made_it"]).split("-"))
            nums |= {float(a), float(b), *(float(x) for x in str(g["minute"]).split("+"))}
            names.add(str(g["scorer"]).lower())
        for r in so_far.get("red_cards") or ():
            nums |= {float(x) for x in str(r["minute"]).split("+")}
            names.add(str(r["player"]).lower())
    forbid = {"comeback_win"} if m.kind == "story_note" and raw.get("facet") == "comebacks" else set()
    prior = max(0, len(goals) - (1 if m.kind in OWN_GOAL_KINDS and goals else 0))
    return Allowed(numbers=nums, scores=scores, names=names, claims=claims_of(m), forbid=forbid,
                   goals=goals if history else [], prior_goals=prior)


# ---- names in Japanese: a katakana word is mapped to the roster by its consonant skeleton ----
# Decision (2026-10-26): a Japanese line may write a player in katakana, as Japanese broadcasts do (イブセン for Ibsen), or in Latin script.
# Both must map to a real player of the moment. Katakana is matched by consonants only, because the vowels a transcription adds (ラスムッセン:
# ra-su-mu-s-se-n) and the long marks carry no information: r/l, b/v, h and w are merged, doubled letters collapse, and a skeleton of four
# consonants or more may differ in one letter (ペトロフ "ptrf" is Petrov "ptrb"). Shorter skeletons must match exactly, under three none is read.
_KANA_CONS = {}
for _row, _cons in (("アイウエオァィゥェォヤユヨャュョワヲヰヱーッ", ""), ("カキクケコ", "k"), ("ガギグゲゴ", "g"), ("サスセソザズゼゾヅ", "s"), ("シ", "s"),
                    ("ジヂ", "j"), ("タテトツ", "t"), ("チ", "c"), ("ダデド", "d"), ("ナニヌネノン", "n"), ("ハヒヘホ", ""), ("フ", "f"),
                    ("バビブベボヴ", "b"), ("パピプペポ", "p"), ("マミムメモ", "m"), ("ラリルレロ", "r")):
    for _k in _row:
        _KANA_CONS[_k] = _cons
_LATIN_RULES = (("sch", "s"), ("tsch", "c"), ("ch", "c"), ("sh", "s"), ("ph", "f"), ("th", "t"), ("ck", "k"), ("qu", "k"), ("q", "k"),
                ("x", "ks"), ("ce", "se"), ("ci", "si"), ("cy", "sy"), ("c", "k"), ("v", "b"), ("w", ""), ("l", "r"), ("z", "s"), ("h", ""), ("y", ""))
# katakana football words that are no names (they never reach the roster match)
JA_LOANWORDS = {"ゴール", "パス", "ボール", "シュート", "ロングボール", "ダイレクト", "サイドチェンジ", "クリア", "ヘディング", "チャンス", "ディフェンス",
                "カウンター", "プレス", "ライン", "キーパー", "ゴールキーパー", "ペナルティ", "エリア", "コーナー", "フリーキック", "スルーパス", "ワンタッチ",
                "トラップ", "ミドル", "サイド", "ピッチ", "チーム", "ホーム", "アウェー", "ゲーム", "ファウル", "カード", "イエロー", "レッド", "オフサイド",
                "ポスト", "バー", "ネット", "セーブ", "ボレー", "ドリブル", "タックル", "インターセプト", "カット", "クロス", "ミドルシュート", "スコア",
                "ゴールネット", "シーズン", "ポイント", "ロング", "ショート", "ショートパス", "ロングパス", "ハーフ", "タッチ", "ファーストタッチ", "スタジアム"}


def skeleton(name: str) -> str:
    """The consonants of a Latin-script name, spelled the way katakana hears them (see above)."""
    t = "".join(c for c in unicodedata.normalize("NFKD", name.lower()) if c.isalpha() and not unicodedata.combining(c))
    t = t.replace("ı", "i")
    for a, b in _LATIN_RULES:
        t = t.replace(a, b)
    t = re.sub(r"[aeiou]", "", t)
    return re.sub(r"(.)\1+", r"\1", t)


def kana_skeleton(word: str) -> str:
    """The consonants of a katakana word."""
    return re.sub(r"(.)\1+", r"\1", "".join(_KANA_CONS.get(c, "") for c in word))


def _near(a: str, b: str) -> bool:
    if len(a) < 3 or len(b) < 3:
        return False
    if min(len(a), len(b)) < 4:
        return a == b
    if abs(len(a) - len(b)) > 1:
        return False
    prev = list(range(len(b) + 1))  # Levenshtein, at most one edit
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1] <= 1


def latin_name_rx(sur: str, lang: str) -> re.Pattern:
    """A surname in a line. Japanese has no spaces, so a Latin name touches kana ("Ibsenが"): only Latin letters bound it there."""
    if lang == "ja":
        return re.compile(rf"(?<![A-Za-zÀ-ÿ]){re.escape(sur)}(?![A-Za-zÀ-ÿ])", re.I)
    return re.compile(rf"(?<!\w){re.escape(sur)}(?!\w)", re.I)


class Verifier:
    def __init__(self, meta: MatchMeta):
        self.meta = meta
        self.players = {surname(p.name).lower(): p.name
                        for t in meta.teams.values() for p in t.players}
        self.team_names = {t.name.lower() for t in meta.teams.values()}
        self.traits: dict[str, set[str]] = {}  # lower-case surname -> trait codes in the roster
        for t in meta.teams.values():
            for p in t.players:
                self.traits.setdefault(surname(p.name).lower(), set()).update(getattr(tr, "value", tr) for tr in (p.traits or []))
        self.skeletons = {sur: skeleton(sur) for sur in self.players}

    def katakana_names(self, text: str) -> dict[str, str]:
        """Katakana words of a line that are a roster surname: word -> lower-case surname (the closest; none for a football word)."""
        out: dict[str, str] = {}
        for word in KATAKANA_RUN.findall(text):
            if word in JA_LOANWORDS or word.rstrip("ー") in JA_LOANWORDS:
                continue
            k = kana_skeleton(word)
            hits = [sur for sur, sk in self.skeletons.items() if _near(k, sk)]
            if hits:
                out[word] = min(hits, key=lambda sur: (self.skeletons[sur] != k, abs(len(self.skeletons[sur]) - len(k)), sur))
        return out

    def named(self, text: str, lang: str) -> set[str]:
        """The roster surnames a line names, in Latin script or, in Japanese, in katakana."""
        low = text.replace("İ", "I").lower()
        out = {sur for sur in self.players if latin_name_rx(sur, lang).search(low)}
        if lang == "ja":
            out |= set(self.katakana_names(text).values())
        return out

    def lang_scores(self, text: str, among: tuple[str, ...] = LANGS) -> dict[str, int] | None:
        """Stop-word hits per language (None: too short to tell)."""
        words = [w.lower() for w in WORD_RE.findall(text) if not KANA_RE.search(w)]
        if len(words) < 5:
            return None
        score = {lang: sum(w in STOPWORDS[lang] for w in words) for lang in among if lang in STOPWORDS}
        if "tr" in score:  # Turkish letters no other language here writes
            score["tr"] += 2 * len(re.findall(r"[ıİğĞşŞ]", text))
        if "es" in score:
            score["es"] += 2 * len(re.findall(r"[ñ¿¡]", text))
        return score

    def detect_lang(self, text: str, among: tuple[str, ...] = LANGS) -> str | None:
        """The language a line looks like, among `among` (the core three by default, which is what en, de and fr channels are checked against;
        a world channel is checked against all nine). Japanese is read from the script: kana is Japanese, whatever else the line holds."""
        if "ja" in among and len(KANA_RE.findall(text)) >= 2:
            return "ja"
        score = self.lang_scores(text, among)
        if score is None:
            return None
        best = max(score, key=score.get)
        return best if score[best] >= 2 and list(score.values()).count(score[best]) == 1 else None

    def claim_violations(self, text: str, lang: str, allowed: Allowed) -> list[Violation]:
        """The claims lexicon (7.5): a tactical phrase needs the matching claim in the facts; a trait phrase needs a player with that
        trait named in the same sentence."""
        out: list[Violation] = []
        for claim, langs in _CLAIM_RX.items():
            m = langs[lang].search(text)
            if m and claim not in allowed.claims:
                out.append(Violation("claim_unsupported", f"'{m.group(0)}' ({claim}) is not in the facts of this moment"))
        for claim in sorted(allowed.forbid):
            m = _FORBID_RX[claim][lang].search(text)
            if m:
                out.append(Violation("claim_unsupported", f"'{m.group(0)}' ({claim}): the record counts points after being behind, not wins"))
        for sentence in SENTENCE_RE.split(text):
            named = self.named(sentence, lang)
            for trait, langs in _TRAIT_RX.items():
                m = langs[lang].search(sentence)
                if m and not any(trait in self.traits[sur] for sur in named):
                    out.append(Violation("trait_unsupported", f"'{m.group(0)}' ({trait}) is said of nobody who has that trait"))
        return out

    def _name_spans(self, text: str, lang: str, surnames: set[str]) -> list[tuple[int, str]]:
        """Where a line names these roster surnames: (offset, lower-case surname), in Latin script or, in Japanese, in katakana."""
        out = [(mt.start(), sur) for sur in surnames for mt in latin_name_rx(sur, lang).finditer(text.replace("İ", "I"))]
        if lang == "ja":
            kana = self.katakana_names(text)
            out += [(mt.start(), kana[mt.group(0)]) for mt in KATAKANA_RUN.finditer(text) if kana.get(mt.group(0)) in surnames]
        return sorted(out)

    def history_violations(self, text: str, masked: str, lang: str, allowed: Allowed) -> list[Violation]:
        """Live runs that joined a running match: the goals so far are facts, but bound to each other. A goal minute belongs to the scorer
        named nearest before it (else after it) in the sentence; after earlier goals no goal is the opener (unless the sentence names the real
        first goal's scorer or team) and the match is not goalless."""
        out: list[Violation] = []
        scorers = {str(g["scorer"]).lower() for g in allowed.goals}
        minutes_of: dict[str, set[int]] = {}
        for g in allowed.goals:
            minutes_of.setdefault(str(g["scorer"]).lower(), set()).add(int(str(g["minute"]).split("+")[0]))
        goal_minutes = set().union(*minutes_of.values()) if minutes_of else set()
        first = allowed.goals[0] if allowed.goals else None
        start = 0
        for sentence in SENTENCE_RE.split(masked):
            at = masked.find(sentence, start)
            start = at + len(sentence)
            real = text[at:at + len(sentence)] if at >= 0 else sentence  # the sentence before score masking, for names
            if allowed.prior_goals:
                m = _GOALLESS_RX[lang].search(real)
                if m:
                    out.append(Violation("history_mismatch", f"'{m.group(0)}': the match has had goals"))
                m = _OPENER_RX[lang].search(real)
                if m:
                    ok = False
                    if first is not None:
                        team = str(first["team"]).lower()
                        low = real.lower()
                        ok = (str(first["scorer"]).lower() in {s for _, s in self._name_spans(real, lang, {str(first["scorer"]).lower()})}
                              or team in low or team.split()[0] in low)
                    if not ok:
                        out.append(Violation("history_mismatch", f"'{m.group(0)}': goals came before this one, it is not the opener"))
            if not goal_minutes:
                continue
            spans = self._name_spans(real, lang, scorers)
            if not spans:
                continue
            for mt in NUM_RE.finditer(sentence):
                value = float(mt.group(0).replace(",", "."))
                if value != int(value) or int(value) not in goal_minutes:
                    continue
                before = [sur for pos, sur in spans if pos < mt.start()]
                who = before[-1] if before else min(spans, key=lambda ps: ps[0] - mt.start())[1]
                if int(value) not in minutes_of.get(who, set()):
                    out.append(Violation("history_mismatch", f"{mt.group(0)}: {self.players.get(who, who)} scored no goal in that minute"))
        return out

    def check(self, text: str, lang: str, allowed: Allowed, max_s: float | None = None, style: str | None = None,
              spelled: bool = False) -> Verdict:
        """`spelled`: numbers written as words must be in the facts too (the newsroom checks every model line so). `style`: a beginner
        line carries no count of anything (the prompt's rule for beginner lines)."""
        v: list[Violation] = []
        if not text.strip():
            return Verdict(False, [Violation("empty", "no text")])
        low = text.lower()

        # scorelines first, so their digits are not judged as loose numbers
        masked = text
        for m in SCORE_RE.finditer(text):
            pair = (int(m.group(1)), int(m.group(2)))
            if pair not in allowed.scores:
                if pair[::-1] in allowed.scores:
                    v.append(Violation("score_swapped", f"{m.group(0)} has home and away reversed; scores are always "
                                       f"home-away, the real scoreline is {pair[1]}-{pair[0]}"))
                else:
                    v.append(Violation("score_mismatch", f"{m.group(0)} is not a real scoreline of this moment"))
            masked = masked.replace(m.group(0), " ")
        for m in NUM_RE.finditer(masked):
            value = float(m.group(0).replace(",", "."))
            if not any(abs(value - a) < 0.006 for a in allowed.numbers):
                v.append(Violation("number_unsupported", f"{m.group(0)} is not in the facts"))

        for sur in sorted(self.named(text, lang)):
            if sur not in allowed.names and not any(sur in t for t in self.team_names):
                v.append(Violation("player_unsupported", f"{self.players[sur]} is not part of this moment"))

        if spelled:
            bad = FORBIDDEN_PUNCT.findall(text)
            if bad:
                v.append(Violation("punctuation", f"{' '.join(sorted(set(bad)))}: no em dash and no middle dot in a line a viewer sees"))
            for m in _NUMWORD_RX[lang].finditer(masked):
                # Turkish capital dotted I lowercases to "i" plus a combining dot, which is no key ("İki" at a sentence start)
                value = _NUMWORD_VALUE[lang].get(m.group(1).replace("İ", "i").lower())
                if value is None:
                    continue
                if not any(abs(value - a) < 0.006 for a in allowed.numbers):
                    v.append(Violation("number_unsupported", f"'{m.group(0)}' ({value}) is not in the facts"))
        if style == "beginner":
            m = _COUNT_RX[lang].search(text)
            if m:
                v.append(Violation("count_in_beginner", f"'{m.group(0)}' is a count; a beginner line says it without counting"))
        v.extend(self.claim_violations(text, lang, allowed))
        v.extend(self.history_violations(text, masked, lang, allowed))

        among = LANGS if lang in LANGS else tuple(STOPWORDS) + ("ja",)
        detected = self.detect_lang(text, among)
        if lang == "ja" and detected is None and len(WORD_RE.findall(text)) >= 5 and not KANA_RE.search(text) \
                and not re.search(r"[\u4e00-\u9fff]", text):
            v.append(Violation("language_mismatch", "expected ja, the line has no Japanese script"))
        if detected and detected != lang and lang not in LANGS and detected != "ja" and lang != "ja":
            score = self.lang_scores(text, among) or {}  # es, it and pt share many function words: a world line is wrong only by a clear margin
            if score.get(detected, 0) - score.get(lang, 0) < 2:
                detected = None
        if detected and detected != lang:
            v.append(Violation("language_mismatch", f"expected {lang}, text looks like {detected}"))
        if max_s is not None and est_seconds(text, lang) > max_s:
            v.append(Violation("too_long", f"{est_seconds(text, lang):.1f}s speech, slot is {max_s:.1f}s"))
        return Verdict(not v, v)
