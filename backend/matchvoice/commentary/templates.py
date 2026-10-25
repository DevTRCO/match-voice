"""Template bank for the fast path (no model).

TEMPLATES[kind][lang][style] is a list of variants ordered short to long, so the
director can pick the longest one that fits the time it has. Every number in a
template comes from a placeholder, never from the text itself.

Voice of the bank: a broadcaster, not a log. The play-by-play kinds are the caller (present tense, short, urgent, a
reaction before an explanation); the analysis kinds are the colour analyst's fallback when the model is unavailable.
At most one number per line, beginner lines carry none except a score. No gendered pronouns for players.
en is British broadcast, de is German TV commentary, fr is French broadcast pace.
"""
from __future__ import annotations

T: dict[str, dict[str, dict[str, list[str]]]] = {
    "kickoff_start": {
        "en": {
            "beginner": ["We're underway!", "And we're off! {home} against {away}.",
                         "Here we go! {home} take on {away}, and the match is under way."],
            "expert": ["We're underway.", "Kick-off, {home} at home to {away}.",
                       "Away we go. {home} host {away}, and we'll see who settles first."],
        },
        "de": {
            "beginner": ["Es geht los!", "Und los geht's! {home} gegen {away}.",
                         "Anpfiff! {home} empfängt {away}, und das Spiel läuft."],
            "expert": ["Anpfiff.", "Anstoß, {home} gegen {away}.",
                       "Das Spiel läuft. {home} zuhause gegen {away}, mal sehen, wer zuerst reinkommt."],
        },
        "fr": {
            "beginner": ["C'est parti !", "Et c'est parti ! {home} contre {away}.",
                         "Le coup d'envoi est donné ! {home} reçoit {away}, et le match est lancé."],
            "expert": ["Coup d'envoi.", "Coup d'envoi, {home} reçoit {away}.",
                       "Le match est lancé. {home} reçoit {away}, voyons qui trouve ses marques."],
        },
    },
    "shot_goal": {
        # the goal call: shouted first, short enough that the analyst's follow-up is voiced right behind it (about 4 s at most)
        "en": {
            "beginner": ["GOAL! {player}!", "It's in! {player} scores for {team}!",
                         "GOAL for {team}! {player} finds the net, it's {score}!"],
            "expert": ["GOAL! {player}!", "{player} scores, {score}.",
                       "GOAL! {player} buries it, and it's {score}!"],
        },
        "de": {
            "beginner": ["TOR! {player}!", "Und der ist drin! {player} trifft für {team}!",
                         "TOR für {team}! {player} netzt ein, es steht {score}!"],
            "expert": ["TOR! {player}!", "{player} trifft, {score}.",
                       "TOR! {player} macht ihn rein, {score}!"],
        },
        "fr": {
            "beginner": ["BUT ! {player} !", "Et c'est dedans ! {player} marque pour {team} !",
                         "BUT pour {team} ! {player} fait mouche, c'est {score} !"],
            "expert": ["BUT ! {player} !", "{player} marque, {score}.",
                       "BUT ! {player} ne tremble pas, {score} !"],
        },
    },
    "shot_saved": {
        "en": {
            "beginner": ["Saved by {keeper}!", "{player} lets fly, and {keeper} gets down to save it!",
                         "{player} strikes it, but {keeper} is equal to it. What a stop!"],
            "expert": ["{keeper} saves!", "{player} hits it, {keeper} keeps it out.",
                       "{keeper} stands tall to deny {player}. What a stop."],
        },
        "de": {
            "beginner": ["Gehalten von {keeper}!", "{player} zieht ab, {keeper} ist da!",
                         "{player} schießt, aber {keeper} fischt den Ball weg. Starke Parade!"],
            "expert": ["{keeper} hält!", "{player} schießt, {keeper} ist zur Stelle.",
                       "{player} zieht ab, aber {keeper} ist hellwach. Stark gehalten."],
        },
        "fr": {
            "beginner": ["Arrêt de {keeper} !", "{player} tire, et {keeper} détourne !",
                         "{player} frappe, mais {keeper} est là. Quel arrêt !"],
            "expert": ["{keeper} repousse !", "{player} frappe, {keeper} s'interpose.",
                       "{player} tente sa chance, mais {keeper} est impérial."],
        },
    },
    "shot_off": {
        "en": {
            "beginner": ["{player} shoots, and it's wide.", "{player} tries it, but it drifts wide.",
                         "Not this time. {player} shoots, and it goes wide of the goal."],
            "expert": ["{player}, wide.", "{player} pulls the trigger, but it's off target.",
                       "{player} has a go, but it misses the frame."],
        },
        "de": {
            "beginner": ["{player} schießt, vorbei.", "{player} versucht es, aber der Ball geht vorbei.",
                         "Daneben. {player} zieht ab, doch der Ball fliegt am Tor vorbei."],
            "expert": ["{player}, vorbei.", "{player} zieht ab, aber der Ball ist nicht auf dem Tor.",
                       "{player} probiert es, doch der Ball segelt am Tor vorbei."],
        },
        "fr": {
            "beginner": ["{player} tire, à côté.", "{player} tente sa chance, mais c'est à côté.",
                         "Pas cette fois. {player} frappe, et le ballon file à côté du but."],
            "expert": ["{player}, à côté.", "{player} déclenche, mais ce n'est pas cadré.",
                       "{player} tente sa chance, mais le ballon passe à côté du cadre."],
        },
    },
    "shot_blocked": {
        "en": {
            "beginner": ["Blocked!", "{player} shoots, but it's blocked!",
                         "{player} fires away, and a defender throws a body in the way!"],
            "expert": ["Blocked.", "{player} shoots, and the defence gets across to block.",
                       "{player} lets fly, but a defender gets a body in the way. Good defending."],
        },
        "de": {
            "beginner": ["Geblockt!", "{player} schießt, aber ein Verteidiger wirft sich dazwischen!",
                         "{player} zieht ab, und ein Verteidiger blockt den Schuss!"],
            "expert": ["Geblockt.", "{player} zieht ab, die Abwehr blockt.",
                       "{player} schießt, doch ein Abwehrbein ist dazwischen. Sauber verteidigt."],
        },
        "fr": {
            "beginner": ["Contré !", "{player} tire, mais un défenseur se met en travers !",
                         "{player} frappe, et un défenseur contre le tir !"],
            "expert": ["Contré.", "{player} frappe, la défense contre.",
                       "{player} tire, mais un défenseur s'interpose. Défense solide."],
        },
    },
    "shot_post": {
        "en": {
            "beginner": ["Off the post!", "{player} hits the post! So close!",
                         "Oh, so close! {player} hits the post, and it stays out!"],
            "expert": ["Off the post!", "{player} rattles the woodwork!",
                       "{player} hits the post, and it stays out. Hard luck."],
        },
        "de": {
            "beginner": ["Pfosten!", "{player} trifft den Pfosten! So knapp!",
                         "Oh, so knapp! {player} setzt den Ball an den Pfosten!"],
            "expert": ["Pfosten!", "{player} trifft das Aluminium!",
                       "{player} trifft den Pfosten, und der Ball bleibt draußen. Pech gehabt."],
        },
        "fr": {
            "beginner": ["Sur le poteau !", "{player} touche le poteau ! Si près !",
                         "Oh, pas loin ! {player} trouve le poteau, et ça reste dehors !"],
            "expert": ["Sur le poteau !", "{player} trouve le montant !",
                       "{player} sur le poteau, et ça ne rentre pas. Pas de chance."],
        },
    },
    "corner": {
        "en": {
            "beginner": ["Corner to {team}.", "Corner for {team}. The ball goes in from the flag."],
            "expert": ["Corner, {team}.", "{team} win a corner. Bodies into the box."],
        },
        "de": {
            "beginner": ["Ecke für {team}.", "Eckball für {team}. Der Ball kommt von der Eckfahne in den Strafraum."],
            "expert": ["Ecke, {team}.", "{team} holt eine Ecke. Alle in den Strafraum."],
        },
        "fr": {
            "beginner": ["Corner pour {team}.", "Corner pour {team}. Le ballon va être joué depuis le coin du terrain."],
            "expert": ["Corner, {team}.", "{team} obtient un corner. Tout le monde dans la surface."],
        },
    },
    "foul": {
        "en": {
            "beginner": ["Foul. Free kick to {team}.", "The whistle goes, and {team} have a free kick."],
            "expert": ["Foul, {team} free kick.", "Referee blows. Free kick to {team}."],
        },
        "de": {
            "beginner": ["Foul. Freistoß für {team}.", "Der Schiedsrichter pfeift, und {team} bekommt einen Freistoß."],
            "expert": ["Foul, Freistoß {team}.", "Pfiff. Freistoß für {team}."],
        },
        "fr": {
            "beginner": ["Faute. Coup franc pour {team}.", "L'arbitre siffle, et {team} obtient un coup franc."],
            "expert": ["Faute, coup franc {team}.", "Coup de sifflet. Coup franc pour {team}."],
        },
    },
    "yellow": {
        "en": {
            "beginner": ["Yellow card, {player}.", "{player} is shown yellow. A yellow card is a warning.",
                         "{player} is booked. A yellow is a warning, and a second one means a red."],
            "expert": ["Yellow for {player}.", "{player} is shown yellow.",
                       "{player} is booked, and {team} have to be careful now."],
        },
        "de": {
            "beginner": ["Gelb für {player}.", "{player} sieht Gelb, eine Verwarnung.",
                         "{player} wird verwarnt. Eine Gelbe ist eine Warnung, die zweite Gelbe bedeutet Rot."],
            "expert": ["Gelb, {player}.", "{player} sieht Gelb.",
                       "{player} sieht Gelb, und {team} muss jetzt aufpassen."],
        },
        "fr": {
            "beginner": ["Jaune pour {player}.", "{player} prend un carton jaune, un avertissement.",
                         "{player} est averti. Un jaune, c'est un avertissement, le deuxième jaune, c'est le rouge."],
            "expert": ["Jaune, {player}.", "{player} est averti.",
                       "{player} prend un jaune, et {team} doit faire attention maintenant."],
        },
    },
    "red": {
        "en": {
            "beginner": ["RED CARD! {player} is off!", "Red card for {player}! {team} are down to {men_en} men!",
                         "That's a red card! {player} has to go, and {team} must play on with {men_en} men."],
            "expert": ["RED CARD! {player} is gone!", "{player} sees red. {team} are down to {men_en}.",
                       "{player} sees red, and {team} must play the rest of the match with {men_en} men."],
        },
        "de": {
            "beginner": ["ROT! {player} muss runter!", "Rote Karte für {player}! {team} spielt jetzt {men_de}!",
                         "Das ist Rot! {player} fliegt vom Platz, und {team} spielt {men_de} weiter."],
            "expert": ["ROT! {player} ist weg!", "{player} sieht Rot. {team} spielt {men_de}.",
                       "{player} sieht Rot, und {team} muss den Rest der Partie {men_de} bestreiten."],
        },
        "fr": {
            "beginner": ["ROUGE ! {player} est expulsé !", "Carton rouge pour {player} ! {team} joue {men_fr} !",
                         "C'est rouge ! {player} doit sortir, et {team} termine {men_fr}."],
            "expert": ["ROUGE ! {player} est exclu !", "{player} prend le rouge. {team} joue {men_fr}.",
                       "{player} prend le rouge, et {team} doit finir le match {men_fr}."],
        },
    },
    "sprint": {
        "en": {
            "beginner": ["{player} is away!", "{player} is flying down the pitch!",
                         "Here goes {player}, flying forward with the ball!"],
            "expert": ["{player} hits {speed} km/h.", "{player} is away, {speed} km/h with the ball."],
        },
        "de": {
            "beginner": ["{player} ist weg!", "{player} rennt los!", "Da geht {player}, mit dem Ball nach vorn!"],
            "expert": ["{player} mit {speed} km/h.", "{player} ist weg, {speed} km/h mit dem Ball."],
        },
        "fr": {
            "beginner": ["{player} est lancé !", "{player} s'échappe !",
                         "Et {player} s'envole, le ballon au pied !"],
            "expert": ["{player} à {speed} km/h.", "{player} est lancé, {speed} km/h balle au pied."],
        },
    },
    "half_time": {
        "en": {
            "beginner": ["Half time. {home} {hg}, {away} {ag}.", "That's the half-time whistle. {home} {hg}, {away} {ag}."],
            "expert": ["Half time: {home} {hg}, {away} {ag}.", "The whistle goes for the break. {home} {hg}, {away} {ag}."],
        },
        "de": {
            "beginner": ["Halbzeit. {home} {hg}, {away} {ag}.", "Das ist die Pause. {home} {hg}, {away} {ag}."],
            "expert": ["Halbzeit: {home} {hg}, {away} {ag}.", "Der Pfiff zur Pause, {home} {hg}, {away} {ag}."],
        },
        "fr": {
            "beginner": ["Mi-temps. {home} {hg}, {away} {ag}.", "C'est la pause. {home} {hg}, {away} {ag}."],
            "expert": ["Mi-temps : {home} {hg}, {away} {ag}.", "Coup de sifflet de la pause, {home} {hg}, {away} {ag}."],
        },
    },
    "full_time": {
        "en": {
            "beginner": ["Full time! {home} {hg}, {away} {ag}.", "And that's the final whistle! It ends {home} {hg}, {away} {ag}."],
            "expert": ["Full time. {home} {hg}, {away} {ag}.", "That's it. {home} {hg}, {away} {ag} at the final whistle."],
        },
        "de": {
            "beginner": ["Abpfiff! {home} {hg}, {away} {ag}.", "Das war's! Es endet {home} {hg}, {away} {ag}."],
            "expert": ["Abpfiff. {home} {hg}, {away} {ag}.", "Aus und vorbei. {home} {hg}, {away} {ag}."],
        },
        "fr": {
            "beginner": ["Fin du match ! {home} {hg}, {away} {ag}.", "C'est terminé ! Score final, {home} {hg}, {away} {ag}."],
            "expert": ["Fin du match. {home} {hg}, {away} {ag}.", "C'est fini. {home} {hg}, {away} {ag} au coup de sifflet final."],
        },
    },
    # analyst moments, used as fallback when the model is unavailable or its line is rejected
    "goal_analysis": {
        "en": {
            "beginner": ["That changes things for {team}.", "That goal changes the whole feel of the game for {team}."],
            "expert": ["The game swings towards {team}.", "That goal lifts {team}'s chance of a win to {win_after} percent."],
        },
        "de": {
            "beginner": ["Das verändert die Partie für {team}.", "Dieses Tor verändert das ganze Spiel für {team}."],
            "expert": ["Das Spiel kippt zugunsten von {team}.", "Die Siegchance von {team} steigt mit diesem Tor auf {win_after} Prozent."],
        },
        "fr": {
            "beginner": ["Ce but change tout pour {team}.", "Ce but change la physionomie du match pour {team}."],
            "expert": ["Le match penche du côté de {team}.", "Ce but fait grimper les chances de victoire de {team} à {win_after} %."],
        },
    },
    "momentum": {
        "en": {
            "beginner": ["{team} are on top right now.", "{team} are really pushing now, and the pressure is building."],
            "expert": ["{team} are pressing the issue.", "{team} have taken control, {shots_n} in the last five minutes."],
        },
        "de": {
            "beginner": ["{team} ist gerade klar am Drücker.", "{team} drückt jetzt, und der Druck wächst."],
            "expert": ["{team} hat das Spiel im Griff.", "{team} übernimmt, {shots_n} in den letzten fünf Minuten."],
        },
        "fr": {
            "beginner": ["{team} domine en ce moment.", "{team} met la pression, et ça se sent."],
            "expert": ["{team} a pris le match en main.", "{team} a pris le contrôle, {shots_n} sur les cinq dernières minutes."],
        },
    },
    "big_save_analysis": {
        "en": {
            "beginner": ["What a save by {keeper}!", "{keeper} keeps that out! That was as good as a goal."],
            "expert": ["{keeper} denies {player}.", "Big save from {keeper}. That was as good as a goal."],
        },
        "de": {
            "beginner": ["Was für eine Parade von {keeper}!", "{keeper} hält das Ding! Das war fast schon ein Tor."],
            "expert": ["{keeper} hält gegen {player}.", "Starke Parade, {keeper}. Das war eine dicke Chance für {player}."],
        },
        "fr": {
            "beginner": ["Quel arrêt de {keeper} !", "{keeper} sort le grand jeu ! C'était presque un but."],
            "expert": ["{keeper} stoppe {player}.", "Gros arrêt de {keeper}. Une occasion énorme pour {player}."],
        },
    },
    "big_chance_analysis": {
        "en": {
            "beginner": ["{player} should have scored there.", "A huge chance goes begging for {player}. That one will hurt."],
            "expert": ["{player} misses a big one.", "{player} should have scored there. That one will hurt."],
        },
        "de": {
            "beginner": ["Da muss {player} treffen.", "Eine Riesenchance für {player}, und der Ball ist nicht drin. Das tut weh."],
            "expert": ["{player} lässt eine ganz dicke liegen.", "Da muss {player} treffen. Eine dicke Chance, und der Ball ist nicht drin."],
        },
        "fr": {
            "beginner": ["{player} devait marquer.", "Énorme occasion pour {player}, et le ballon n'est pas rentré. Ça va faire mal."],
            "expert": ["{player} manque l'immanquable.", "{player} devait marquer, et l'occasion est gâchée."],
        },
    },
    "shot_milestone": {
        "en": {
            "beginner": ["{player} keeps firing.", "{player} has another go. That is a lot of shots from one player."],
            "expert": ["{shots} shots for {player}.", "{player} is up to {shots} shots now, and still looking for it."],
        },
        "de": {
            "beginner": ["{player} schießt schon wieder.", "{player} bleibt dran und probiert es immer wieder."],
            "expert": ["{shots} Schüsse für {player}.", "{player} steht bei {shots} Schüssen und sucht weiter."],
        },
        "fr": {
            "beginner": ["{player} insiste.", "{player} retente sa chance, encore et encore."],
            "expert": ["{shots} tirs pour {player}.", "{player} en est à {shots} tirs, et cherche encore."],
        },
    },
    "pass_final_third": {
        "en": {
            "beginner": ["{player} plays it forward.", "{player} to {receiver}, and the attack is on the move."],
            "expert": ["{player} to {receiver}.", "{player} finds {receiver} in the final third.",
                       "{player} picks out {receiver}, and the move is into the final third."],
        },
        "de": {
            "beginner": ["{player} spielt nach vorn.", "{player} auf {receiver}, und der Angriff rollt."],
            "expert": ["{player} auf {receiver}.", "{player} findet {receiver} im letzten Drittel.",
                       "{player} bedient {receiver}, und das Spiel geht ins letzte Drittel."],
        },
        "fr": {
            "beginner": ["{player} joue vers l'avant.", "{player} pour {receiver}, et l'attaque est lancée."],
            "expert": ["{player} pour {receiver}.", "{player} trouve {receiver} dans le dernier tiers.",
                       "{player} sert {receiver}, et le jeu entre dans le dernier tiers."],
        },
    },
    "tackle_won": {
        "en": {
            "beginner": ["{player} wins it.", "Great tackle from {player}, and the ball is won back."],
            "expert": ["{player} wins it back.", "Strong challenge from {player}, and {team} have the ball back."],
        },
        "de": {
            "beginner": ["{player} holt sich den Ball.", "Starker Zweikampf von {player}, der Ball ist zurück."],
            "expert": ["{player} gewinnt ihn.", "Starkes Tackling von {player}, {team} hat den Ball wieder."],
        },
        "fr": {
            "beginner": ["{player} récupère le ballon.", "Beau tacle de {player}, le ballon est récupéré."],
            "expert": ["{player} le gagne.", "Beau duel de {player}, et {team} récupère le ballon."],
        },
    },
    "long_ball": {
        "en": {
            "beginner": ["{player} goes long.", "{player} sends it long, towards {receiver}.",
                         "A big ball forward from {player}, and {receiver} gets there."],
            "expert": ["{player} goes long.", "{player} hits it long for {receiver}.",
                       "{player} launches it forward, and {receiver} gets onto it."],
        },
        "de": {
            "beginner": ["{player} schlägt ihn lang.", "{player} schlägt ihn weit nach vorn, auf {receiver}.",
                         "Ein langer Ball von {player}, und {receiver} kommt dran."],
            "expert": ["{player} schlägt ihn lang.", "{player} schlägt ihn lang auf {receiver}.",
                       "{player} schlägt ihn weit nach vorn, und {receiver} kommt ran."],
        },
        "fr": {
            "beginner": ["{player} balance un long ballon.", "{player} envoie le ballon loin devant, vers {receiver}.",
                         "Grand ballon de {player}, et {receiver} le récupère."],
            "expert": ["{player} joue long.", "{player} lance en profondeur vers {receiver}.",
                       "{player} envoie un long ballon, et {receiver} le prend."],
        },
    },
    # ---------- the fast layer: the caller's fragments (docs/DATA-MODEL.md 7.1), at most 6 words (en) and 7 (de, fr) ----------
    # The volume is names and verbs: who has the ball, who plays it to whom, what kind of pass. A wording with a player placeholder names a
    # player, the others are name-less and exist only where the ball itself is worth a word (a chested ball, a switch, a clearance); the builder
    # decides which kind a moment gets. A pitch zone is said rarely and in one order (the builder passes `third` and `wing` only then). Words for
    # codes (direction, pass type, side) and clauses (`{note}`, `{bare}`) come from WORDS. In a live run the director takes the wording of its kind
    # that was used longest ago (the longest on a tie), so the longest wordings set the length of a typical fragment.
    "touch": {
        # `dir` is the direction of the pass that ARRIVED (how the ball came to the receiver), never what the receiver does next: the wordings say
        # "Forward to X", never "X, forward". `kicker` is the player who played it, `note` and `bare` say how the receiver took it (control, chest,
        # head), `back_word` is there when he receives it facing his own goal. `third` and `wing` say where he stands, only on a rare turn.
        "en": {
            "beginner": ["{player} has it now.", "It's {player} on the ball.", "{Dir_word} to {player}.", "{player} {note}.", "{player} gets on the ball.",
                         "{player} gets it from {kicker}.", "{player} is {third_word}.", "{player} is {wing_word}.",
                         "{bare}.", "{bare}, {back_word}."],
            "expert": ["{player}.", "{player} has it.", "{Dir_word} to {player}.", "{player} {note}.", "{player} on the ball.", "{player}, from {kicker}.",
                       "{player} {third_word}.", "{player}, {wing_word}.", "{bare}.", "{bare}, {back_word}."],
        },
        "de": {
            "beginner": ["{player} hat den Ball jetzt.", "Jetzt hat {player} den Ball.", "{Dir_word} auf {player}.", "{player} {note}.", "{player} kommt an den Ball.",
                         "{player} bekommt ihn von {kicker}.", "{player} steht {third_word}.", "{player} steht {wing_word}.",
                         "{bare}.", "{bare}, {back_word}."],
            "expert": ["{player}.", "{player} hat ihn.", "{Dir_word} auf {player}.", "{player} {note}.", "{player} am Ball.", "{player}, zugespielt von {kicker}.",
                       "{player} {third_word}.", "{player}, {wing_word}.", "{bare}.", "{bare}, {back_word}."],
        },
        "fr": {
            "beginner": ["{player} a le ballon maintenant.", "C'est {player} qui a le ballon.", "{Dir_word} pour {player}.", "{player} {note}.", "{player} touche le ballon.",
                         "{player}, servi par {kicker}.", "{player} est {third_word}.", "{player} est {wing_word}.",
                         "{bare}.", "{bare}, {back_word}."],
            "expert": ["{player}.", "{player} a le ballon.", "{Dir_word} pour {player}.", "{player} {note}.", "{player} au ballon.", "{player}, servi par {kicker}.",
                       "{player} {third_word}.", "{player}, {wing_word}.", "{bare}.", "{bare}, {back_word}."],
        },
    },
    "pass_kind": {
        # A routine short pass has no `pass_type`: the kick names the kicker only ("X plays it on."), with what the kick shows when it shows something
        # (`pressed_word`: he is closed down, `driven_word`: a hard low ball), and the receipt then names the receiver ("Inside to Y."), so each name is said once.
        # A pass with a type says the type and always its target ("Long ball for Tavares"), except a clearance, which has none. Never how it ends,
        # never a verdict (no "good ball", no "they keep it"), never the path of the ball ("down the left" would be read as one: `lane` is where the kick
        # starts). The name-less wordings are for the types a caster may leave unnamed.
        "en": {
            "beginner": ["{player} plays it on.", "{player} moves it on.", "{player} passes it on.", "{player} moves it along.", "{player} knocks it along.",
                         "{player} sends it on.",
                         "{player}, {pressed_word}, plays it on.", "{player} {driven_word}.", "{Pressed_word}, plays it on.", "Played on {pressed_word}.", "Moved on {pressed_word}.", "Passed on {pressed_word}.",
                         "Released {pressed_word}.", "{driven_bare}.", "{driven_alt}.",
                         "{Pass_done} {pass_prep} {target}.", "{player} {pass_verb} {pass_prep} {target}.", "{Pass_word} {pass_prep} {target}.", "{Pass_prep} {target}.",
                         "{player} {pass_verb}.", "{Pass_done}.", "{Pass_word}.", "{Pass_done} {lane_word}."],
            "expert": ["{player} plays it on.", "{player} moves it on.", "{player} moves it along.", "{player} knocks it along.", "{player} recycles it.",
                       "{player}, {pressed_word}, plays it on.", "{player} {driven_word}.", "{Pressed_word}, plays it on.", "Played on {pressed_word}.", "Moved on {pressed_word}.", "Passed on {pressed_word}.",
                         "Released {pressed_word}.", "{driven_bare}.", "{driven_alt}.",
                       "{Pass_done} {pass_prep} {target}.", "{player} {pass_verb} {pass_prep} {target}.", "{Pass_word} {pass_prep} {target}.", "{Pass_prep} {target}.",
                       "{player} {pass_verb}.", "{Pass_done}.", "{Pass_word}.", "{Pass_done} {lane_word}."],
        },
        "de": {
            "beginner": ["{player} spielt ab.", "{player} gibt ihn weiter.", "{player} leitet ihn weiter.", "{player} spielt ihn weiter.", "{player} schickt ihn weiter.",
                         "{player} lässt den Ball laufen.",
                         "{player}, {pressed_word}, spielt ab.", "{player} {driven_word}.", "{Pressed_word} weitergespielt.", "Abgespielt {pressed_word}.", "Weitergegeben {pressed_word}.", "Losgeworden {pressed_word}.",
                         "{driven_bare}.", "{driven_alt}.",
                         "{Pass_done} {pass_prep} {target}.", "{player} {pass_verb} {pass_prep} {target}.", "{Pass_word} {pass_prep} {target}.", "{Pass_prep} {target}.",
                         "{player} {pass_verb}.", "{Pass_done}.", "{Pass_word}.", "{Pass_done} {lane_word}."],
            "expert": ["{player} spielt ab.", "{player} gibt ihn weiter.", "{player} leitet ihn weiter.", "{player} lässt ihn laufen.", "{player} hält ihn in Bewegung.",
                       "{player}, {pressed_word}, spielt ab.", "{player} {driven_word}.", "{Pressed_word} weitergespielt.", "Abgespielt {pressed_word}.", "Weitergegeben {pressed_word}.", "Losgeworden {pressed_word}.",
                         "{driven_bare}.", "{driven_alt}.",
                       "{Pass_done} {pass_prep} {target}.", "{player} {pass_verb} {pass_prep} {target}.", "{Pass_word} {pass_prep} {target}.", "{Pass_prep} {target}.",
                       "{player} {pass_verb}.", "{Pass_done}.", "{Pass_word}.", "{Pass_done} {lane_word}."],
        },
        "fr": {
            "beginner": ["{player} la joue.", "{player} fait circuler.", "{player} relance le jeu.", "{player} passe le ballon.", "{player} transmet le ballon.",
                         "{player} joue simple.",
                         "{player}, {pressed_word}, la joue.", "{player} {driven_word}.", "{Pressed_word}, la joue.", "Joué {pressed_word}.", "Passé {pressed_word}.", "Relancé {pressed_word}.",
                         "{driven_bare}.", "{driven_alt}.",
                         "{Pass_done} {pass_prep} {target}.", "{player} {pass_verb} {pass_prep} {target}.", "{Pass_word} {pass_prep} {target}.", "{Pass_prep} {target}.",
                         "{player} {pass_verb}.", "{Pass_done}.", "{Pass_word}.", "{Pass_done} {lane_word}."],
            "expert": ["{player} la joue.", "{player} fait circuler.", "{player} relance le jeu.", "{player} distribue.", "{player} joue simple.",
                       "{player}, {pressed_word}, la joue.", "{player} {driven_word}.", "{Pressed_word}, la joue.", "Joué {pressed_word}.", "Passé {pressed_word}.", "Relancé {pressed_word}.",
                         "{driven_bare}.", "{driven_alt}.",
                       "{Pass_done} {pass_prep} {target}.", "{player} {pass_verb} {pass_prep} {target}.", "{Pass_word} {pass_prep} {target}.", "{Pass_prep} {target}.",
                       "{player} {pass_verb}.", "{Pass_done}.", "{Pass_word}.", "{Pass_done} {lane_word}."],
        },
    },
    "carry": {
        "en": {
            "beginner": ["{player} runs with it.", "{player} carries it forward.", "A good run forward.", "Space to run into."],
            "expert": ["{player} drives on.", "{player} carries it forward.", "Strong carry there.", "{player} drives on, looking for space.",
                       "Up the pitch it goes."],
        },
        "de": {
            "beginner": ["{player} läuft los.", "{player} treibt den Ball nach vorn.", "Ein starker Lauf nach vorn.", "Da ist Platz zum Laufen."],
            "expert": ["{player} zieht an.", "{player} marschiert mit dem Ball.", "Starker Vorstoß.", "{player} zieht an und sucht den Raum.",
                       "Es geht nach vorn."],
        },
        "fr": {
            "beginner": ["{player} part balle au pied.", "{player} avance avec le ballon.", "Une belle course vers l'avant.", "De l'espace pour avancer."],
            "expert": ["{player} emmène le ballon.", "{player} accélère.", "Belle percée.", "{player} accélère et cherche l'espace.",
                       "Ça avance vers l'avant."],
        },
    },
    "take_on": {
        "en": {
            "beginner": ["{player} {note}.", "{player} {note}, one on one."],
            "expert": ["{player} {note}.", "One on one: {player} {note}."],
        },
        "de": {
            "beginner": ["{player} {note}.", "{player} {note}, eins gegen eins."],
            "expert": ["{player} {note}.", "Eins gegen eins: {player} {note}."],
        },
        "fr": {
            "beginner": ["{player} {note}.", "{player} {note}, un contre un."],
            "expert": ["{player} {note}.", "Un contre un : {player} {note}."],
        },
    },
    "duel": {
        "en": {
            "beginner": ["{winner} {note}.", "{bare}, by {winner}.", "{bare}.", "Good defending."],
            "expert": ["{winner} {note}.", "{bare}, by {winner}.", "{bare}.", "Good defending."],
        },
        "de": {
            "beginner": ["{winner} {note}.", "{bare} von {winner}.", "{bare}.", "Gut verteidigt."],
            "expert": ["{winner} {note}.", "{bare} von {winner}.", "{bare}.", "Gut verteidigt."],
        },
        "fr": {
            "beginner": ["{winner} {note}.", "{bare} par {winner}.", "{bare}.", "Belle défense."],
            "expert": ["{winner} {note}.", "{bare} par {winner}.", "{bare}.", "Belle défense."],
        },
    },
    "press_on": {
        # the expert wording says "high" only when the presser is in the opponent's half (facet high), see WORDS["press_on"]
        "en": {
            "beginner": ["{presser} chases the ball.", "{presser} runs at the ball carrier."],
            "expert": ["{presser} closing in.", "{presser} {note}."],
        },
        "de": {
            "beginner": ["{presser} läuft an.", "{presser} geht schnell auf den Ball."],
            "expert": ["{presser} setzt nach.", "{presser} {note}."],
        },
        "fr": {
            "beginner": ["{presser} court sur le ballon.", "{presser} va vite sur le porteur."],
            "expert": ["{presser} met la pression.", "{presser} {note}."],
        },
    },
    "in_behind": {
        "en": {
            "beginner": ["{runner} is through!", "{runner} is clear!"],
            "expert": ["{runner} in behind!", "{runner} is away!"],
        },
        "de": {
            "beginner": ["{runner} ist frei!", "{runner} läuft allein los!"],
            "expert": ["{runner} in der Tiefe!", "{runner} ist durch!"],
        },
        "fr": {
            "beginner": ["{runner} est dans la course !", "{runner} file seul !"],
            "expert": ["{runner} dans le dos !", "{runner} est lancé !"],
        },
    },
    "line_break": {
        "en": {
            "beginner": ["{player} finds {receiver}.", "A pass that cuts out the middle."],
            "expert": ["Splits the lines, {receiver}.", "{player} breaks the lines."],
        },
        "de": {
            "beginner": ["{player} findet {receiver}.", "Ein Pass, der die Mitte überspringt."],
            "expert": ["Linien durchbrochen, {receiver}.", "{player} bricht die Linien."],
        },
        "fr": {
            "beginner": ["{player} trouve {receiver}.", "Une passe qui saute le milieu."],
            "expert": ["Lignes brisées, {receiver}.", "{player} casse les lignes."],
        },
    },
    "block": {
        "en": {"beginner": ["{bare}!", "{note}!"], "expert": ["{bare}!", "{note}!"]},
        "de": {"beginner": ["{bare}!", "{note}!"], "expert": ["{bare}!", "{note}!"]},
        "fr": {"beginner": ["{bare} !", "{note} !"], "expert": ["{bare} !", "{note} !"]},
    },
    "restart": {
        "en": {
            "beginner": ["{note}.", "{bare}, and {team} take it.", "{why}."],
            "expert": ["{note}.", "{bare}, {team}."],
        },
        "de": {
            "beginner": ["{note}.", "{bare}, {team} führt aus.", "{why}."],
            "expert": ["{note}.", "{bare}, {team}."],
        },
        "fr": {
            "beginner": ["{note}.", "{bare}, {team} le joue.", "{why}."],
            "expert": ["{note}.", "{bare}, {team}."],
        },
    },
    "setpiece_setup": {
        "en": {
            "beginner": ["{taker} will take it.", "{taker} steps up to take it."],
            "expert": ["{taker} over it.", "{taker} stands over it."],
        },
        "de": {
            "beginner": ["{taker} führt den Freistoß aus.", "{taker} tritt an."],
            "expert": ["{taker} legt ihn sich zurecht.", "{taker} steht über dem Ball."],
        },
        "fr": {
            "beginner": ["{taker} va tirer le coup franc.", "{taker} se prépare."],
            "expert": ["{taker} au ballon.", "{taker} se place derrière le ballon."],
        },
    },
    "duel_1v1": {
        "en": {
            "beginner": ["{attacker} against {defender}.", "{attacker} takes on {defender}."],
            "expert": ["{attacker} one on one with {defender}.", "{attacker} against {defender}."],
        },
        "de": {
            "beginner": ["{attacker} gegen {defender}.", "{attacker} fordert {defender} heraus."],
            "expert": ["{attacker} allein gegen {defender}.", "{attacker} gegen {defender}."],
        },
        "fr": {
            "beginner": ["{attacker} face à {defender}.", "{attacker} défie {defender}."],
            "expert": ["{attacker} seul face à {defender}.", "{attacker} face à {defender}."],
        },
    },
    # ---------- the context layer: the colour analyst's template lines (7.2). The first wording is the one for open play (the
    # director takes the shortest while the ball is in play), the last is for a dead ball (the longest). A second wording exists only where
    # the facts support a longer sentence (`{note_long}`: the move, the tally, the score with the shots, a stat against the other side); a kind
    # with nothing more to say has one. No wording announces the occasion ("while the ball is dead, ...") or opens with a lead like "worth
    # noting": no caster says that, the fact is the sentence. Every clause comes from WORDS ----------
    "player_note": {
        "en": {"beginner": ["{player} {note}.", "{player} of {team} {note} and {also}.", "{player} of {team} {note}, {also} and {more}."],
               "expert": ["{player} {note}.", "{player} of {team} {note} and {also}.", "{player} of {team} {note}, {also} and {more}."]},
        "de": {"beginner": ["{player} {note}.", "{player} von {team} {note} und {also}.", "{player} von {team} {note}, {also} und {more}."],
               "expert": ["{player} {note}.", "{player} von {team} {note} und {also}.", "{player} von {team} {note}, {also} und {more}."]},
        "fr": {"beginner": ["{player} {note}.", "{player}, de {team}, {note} et {also}.", "{player}, de {team}, {note}, {also} et {more}."],
               "expert": ["{player} {note}.", "{player}, de {team}, {note} et {also}.", "{player}, de {team}, {note}, {also} et {more}."]},
    },
    "counter_note": {
        "en": {"beginner": ["{note}.", "{note_long}."], "expert": ["{note}.", "{note_long}."]},
        "de": {"beginner": ["{note}.", "{note_long}."], "expert": ["{note}.", "{note_long}."]},
        "fr": {"beginner": ["{note}.", "{note_long}."], "expert": ["{note}.", "{note_long}."]},
    },
    "fatigue_note": {
        "en": {
            "beginner": ["{player} is getting tired.", "{player} has run a lot, and it shows."],
            "expert": ["{player} is starting to tire.", "The legs are going for {player}."],
        },
        "de": {
            "beginner": ["{player} wird müde.", "{player} ist viel gelaufen, das sieht man."],
            "expert": ["{player} wird langsam müde.", "{player} sind die Beine schwer geworden."],
        },
        "fr": {
            "beginner": ["{player} fatigue.", "{player} a beaucoup couru, ça se voit."],
            "expert": ["{player} commence à accuser le coup.", "{player} a les jambes lourdes."],
        },
    },
    "tempo_note": {
        "en": {"beginner": ["{note}.", "{note_long}."], "expert": ["{note}.", "{note_long}."]},
        "de": {"beginner": ["{note}.", "{note_long}."], "expert": ["{note}.", "{note_long}."]},
        "fr": {"beginner": ["{note}.", "{note_long}."], "expert": ["{note}.", "{note_long}."]},
    },
    "press_note": {
        "en": {"beginner": ["{note}."], "expert": ["{note}."]},
        "de": {"beginner": ["{note}."], "expert": ["{note}."]},
        "fr": {"beginner": ["{note}."], "expert": ["{note}."]},
    },
    "story_note": {  # the dossier: expert gets the fact, beginner gets it with a word of why it matters
        "en": {"beginner": ["{bare}."], "expert": ["{note}."]},
        "de": {"beginner": ["{bare}."], "expert": ["{note}."]},
        "fr": {"beginner": ["{bare}."], "expert": ["{note}."]},
    },
    "phase_note": {
        "en": {"beginner": ["{note}."], "expert": ["{note}."]},
        "de": {"beginner": ["{note}."], "expert": ["{note}."]},
        "fr": {"beginner": ["{note}."], "expert": ["{note}."]},
    },
    "shape_note": {
        "en": {"beginner": ["{note}."], "expert": ["{note}."]},
        "de": {"beginner": ["{note}."], "expert": ["{note}."]},
        "fr": {"beginner": ["{note}."], "expert": ["{note}."]},
    },
}

# Placeholders that carry a player's name. A wording with one of them names a player (name rationing, docs/DATA-MODEL.md 7.1).
NAME_KEYS = ("player", "target", "defender", "winner", "presser", "runner", "taker", "attacker", "receiver", "keeper", "kicker", "assist", "chain_text")

# Words that fill the fast and context templates, one table per code. Helper tables (dir, side, pass, ...) become `<name>_word`
# params, a table named like a kind with a `facet` param becomes the clause `{note}` (and `{bare}` when a `<kind>_bare` table
# exists). Clauses are third person without a pronoun, so one clause serves both styles. No digits, no dashes, no numbers: counts
# arrive as `nth_word` / `n_word` / `goals_word` from the params.
WORDS: dict[str, dict[str, dict[str, str]]] = {
    "dir": {
        "en": {"forward": "forward", "back": "back", "inside": "inside", "wide": "wide"},
        "de": {"forward": "nach vorn", "back": "zurück", "inside": "nach innen", "wide": "nach außen"},
        "fr": {"forward": "vers l'avant", "back": "en retrait", "inside": "dans l'axe", "wide": "sur l'aile"},
    },
    "side": {
        "en": {"left": "left", "right": "right", "centre": "middle"},
        "de": {"left": "links", "right": "rechts", "centre": "in der Mitte"},
        "fr": {"left": "à gauche", "right": "à droite", "centre": "dans l'axe"},
    },
    "pass": {
        "en": {"switch": "switch", "through": "through ball", "cross": "cross", "long": "long ball", "lay_off": "lay-off", "back": "back-pass", "first_time": "one-touch pass", "short": "short pass",
               "cut_back": "cut-back", "clearance": "clearance"},
        "de": {"switch": "Seitenwechsel", "through": "Steilpass", "cross": "Flanke", "long": "langer Ball", "lay_off": "Ablage", "back": "Rückpass", "first_time": "Direktpass", "short": "kurzer Pass",
               "cut_back": "Zurücklegen", "clearance": "Befreiungsschlag"},
        "fr": {"switch": "renversement", "through": "passe en profondeur", "cross": "centre", "long": "long ballon", "lay_off": "remise",
               "back": "passe en retrait", "first_time": "passe en une touche",
               "short": "passe courte", "cut_back": "remise en retrait", "clearance": "dégagement"},
    },
    "pass_verb": {
        "en": {"switch": "switches it", "through": "slips it through", "cross": "whips it in", "long": "goes long", "lay_off": "lays it off",
               "back": "plays it back", "first_time": "one-touches it",
               "short": "plays it short", "cut_back": "cuts it back", "clearance": "clears it"},
        "de": {"switch": "verlagert das Spiel", "through": "steckt durch", "cross": "flankt", "long": "schlägt ihn lang", "lay_off": "legt ab",
               "back": "spielt zurück", "first_time": "spielt direkt weiter",
               "short": "spielt kurz", "cut_back": "legt zurück", "clearance": "schlägt ihn weg"},
        "fr": {"switch": "renverse le jeu", "through": "met en profondeur", "cross": "centre", "long": "joue long", "lay_off": "remet",
               "back": "relance en retrait", "first_time": "joue en une touche",
               "short": "joue court", "cut_back": "remet en retrait", "clearance": "dégage"},
    },
    "pass_done": {  # the kick as a fragment, what the ball does when it leaves the foot (no verdict, no outcome)
        "en": {"switch": "Switched", "through": "Slipped through", "cross": "Whipped in", "long": "Hit long", "lay_off": "Laid off",
               "back": "Played back", "first_time": "One touch", "short": "Played short", "cut_back": "Cut back", "clearance": "Cleared"},
        "de": {"switch": "Verlagert", "through": "Durchgesteckt", "cross": "Geflankt", "long": "Lang geschlagen", "lay_off": "Abgelegt",
               "back": "Zurückgespielt", "first_time": "Direkt gespielt", "short": "Kurz gespielt", "cut_back": "Zurückgelegt", "clearance": "Weggeschlagen"},
        "fr": {"switch": "Jeu renversé", "through": "Mis en profondeur", "cross": "Centré", "long": "Joué long", "lay_off": "Remis",
               "back": "Renvoyé en retrait", "first_time": "Une touche", "short": "Joué court", "cut_back": "Remis en retrait", "clearance": "Dégagé"},
    },
    "lane": {  # the flank the kick leaves from, in the kicker's attacking direction ("from", never "down": the table says nothing about where the ball goes)
        "en": {"left": "from the left", "right": "from the right", "centre": "from the middle"},
        "de": {"left": "von links", "right": "von rechts", "centre": "aus der Mitte"},
        "fr": {"left": "depuis la gauche", "right": "depuis la droite", "centre": "depuis l'axe"},
    },
    "third": {  # where the player stands when the ball arrives (a receipt) or leaves (a kick), in his side's attacking direction
        "en": {"own": "in their own third", "mid": "in the middle third", "final": "in the final third"},
        "de": {"own": "im eigenen Drittel", "mid": "im mittleren Drittel", "final": "im letzten Drittel"},
        "fr": {"own": "dans son propre tiers", "mid": "dans le tiers médian", "final": "dans le dernier tiers"},
    },
    "wing": {  # the third of the width he stands in
        "en": {"left": "out on the left", "right": "out on the right", "centre": "in the middle"},
        "de": {"left": "links außen", "right": "rechts außen", "centre": "in der Mitte"},
        "fr": {"left": "sur le côté gauche", "right": "sur le côté droit", "centre": "dans l'axe"},
    },
    "touch": {  # how the receiver took the ball (the `facet` of a touch), after his name
        "en": {"control": "takes it down", "chest": "chests it down", "head": "heads it on"},
        "de": {"control": "nimmt ihn an", "chest": "nimmt ihn mit der Brust an", "head": "köpft ihn weiter"},
        "fr": {"control": "contrôle le ballon", "chest": "amortit de la poitrine", "head": "dévie de la tête"},
    },
    "touch_bare": {  # the same without the name: only said for a ball worth a word (a chested ball, a header, a ball taken with the back to goal)
        "en": {"control": "Taken down", "chest": "Chested down", "head": "Headed on"},
        "de": {"control": "Angenommen", "chest": "Brustannahme", "head": "Weitergeköpft"},
        "fr": {"control": "Contrôlé", "chest": "Amorti de la poitrine", "head": "Dévié de la tête"},
    },
    "pass_prep": {  # the preposition that takes the target of a pass of this type: "goes long for X", "switches it to X"
        "en": {"switch": "to", "through": "to", "cross": "for", "long": "for", "lay_off": "to", "back": "to", "first_time": "to", "short": "to",
               "cut_back": "for", "clearance": "to"},
        "de": {"switch": "auf", "through": "auf", "cross": "auf", "long": "auf", "lay_off": "auf", "back": "zu", "first_time": "auf", "short": "zu",
               "cut_back": "auf", "clearance": "auf"},
        "fr": {"switch": "vers", "through": "pour", "cross": "pour", "long": "vers", "lay_off": "pour", "back": "vers", "first_time": "pour", "short": "pour",
               "cut_back": "pour", "clearance": "vers"},
    },
    "extra": {  # what the kick or the receipt shows besides its type: closed down, hit hard and low, received facing the own goal
        "en": {"pressed": "under pressure", "driven": "drives it", "back": "back to goal", "driven_bare": "Hit hard and low", "driven_alt": "Driven in low and hard"},
        "de": {"pressed": "unter Druck", "driven": "spielt ihn scharf", "back": "mit dem Rücken zum Tor", "driven_bare": "Scharf gespielt", "driven_alt": "Flach und hart gespielt"},
        "fr": {"pressed": "sous pression", "driven": "joue sèchement", "back": "dos au but", "driven_bare": "Joué sèchement", "driven_alt": "Joué fort et à ras de terre"},
    },
    "nth": {
        "en": {"2": "second", "3": "third", "4": "fourth", "5": "fifth", "6": "sixth", "7": "seventh", "8": "eighth"},
        "de": {"2": "zweite", "3": "dritte", "4": "vierte", "5": "fünfte", "6": "sechste", "7": "siebte", "8": "achte"},
        "fr": {"2": "deuxième", "3": "troisième", "4": "quatrième", "5": "cinquième", "6": "sixième", "7": "septième", "8": "huitième"},
    },
    # ---- clauses by kind and facet ----
    "take_on": {
        "en": {"won": "goes past {defender}", "lost": "is stopped by {defender}"},
        "de": {"won": "geht an {defender} vorbei", "lost": "scheitert an {defender}"},
        "fr": {"won": "passe {defender}", "lost": "est stoppé par {defender}"},
    },
    "duel": {
        "en": {"interception": "cuts it out", "aerial": "wins the header", "ground": "wins the duel"},
        "de": {"interception": "fängt ihn ab", "aerial": "gewinnt das Kopfballduell", "ground": "gewinnt den Zweikampf"},
        "fr": {"interception": "intercepte", "aerial": "gagne le duel aérien", "ground": "gagne son duel"},
    },
    "duel_bare": {
        "en": {"interception": "Cut out", "aerial": "Won in the air", "ground": "Won it"},
        "de": {"interception": "Abgefangen", "aerial": "Kopfball gewonnen", "ground": "Zweikampf gewonnen"},
        "fr": {"interception": "Intercepté", "aerial": "Gagné dans les airs", "ground": "Duel gagné"},
    },
    "block": {
        "en": {"block": "Blocked by {player}", "clearance": "Cleared by {player}"},
        "de": {"block": "Geblockt von {player}", "clearance": "Geklärt von {player}"},
        "fr": {"block": "Contré par {player}", "clearance": "Dégagé par {player}"},
    },
    "block_bare": {
        "en": {"block": "Blocked", "clearance": "Cleared"},
        "de": {"block": "Geblockt", "clearance": "Geklärt"},
        "fr": {"block": "Contré", "clearance": "Dégagé"},
    },
    "press_on": {  # high: the presser is in the opponent's half; low: anywhere else (no claim about the height)
        "en": {"high": "presses high", "low": "gets tight"},
        "de": {"high": "läuft früh an", "low": "geht eng drauf"},
        "fr": {"high": "presse haut", "low": "reste au contact du porteur"},
    },
    "restart": {
        "en": {"throw_in": "Throw on the {side_word} for {team}", "goal_kick": "Goal kick for {team}",
               "free_kick": "Free kick for {team}", "kickoff": "{team} get us going again"},
        "de": {"throw_in": "Einwurf {side_word} für {team}", "goal_kick": "Abstoß für {team}",
               "free_kick": "Freistoß für {team}", "kickoff": "{team} stößt wieder an"},
        "fr": {"throw_in": "Touche {side_word} pour {team}", "goal_kick": "Six mètres pour {team}",
               "free_kick": "Coup franc pour {team}", "kickoff": "{team} remet en jeu"},
    },
    "restart_why": {  # the beginner's explanation: why this restart, in terms of what happened
        "en": {"throw_in": "The ball went out over the touchline, so {team} throw it back in",
               "goal_kick": "The ball went out over the goal line, so {team} restart with a goal kick",
               "free_kick": "There was a foul, so the referee gives {team} a free kick and they take it from where it happened",
               "kickoff": "The ball goes back to the centre circle, and {team} get the game going again"},
        "de": {"throw_in": "Der Ball war über die Seitenlinie, deshalb wirft {team} ihn wieder ein",
               "goal_kick": "Der Ball ging über die Torlinie hinaus, deshalb bekommt {team} den Abstoß zugesprochen",
               "free_kick": "Nach einem Foul bekommt {team} einen Freistoß und darf das Spiel von dort aus fortsetzen",
               "kickoff": "Der Ball liegt wieder im Anstoßkreis, und {team} bringt das Spiel wieder in Gang"},
        "fr": {"throw_in": "Le ballon est sorti sur la touche, alors {team} le remet en jeu à la main",
               "goal_kick": "Le ballon est sorti derrière la ligne de but, alors {team} relance depuis les six mètres",
               "free_kick": "Une faute a été sifflée, alors l'arbitre accorde un coup franc à {team} à l'endroit de la faute",
               "kickoff": "Le ballon retourne au centre du terrain, et {team} remet le match en route"},
    },
    "restart_bare": {
        "en": {"throw_in": "Throw-in", "goal_kick": "Goal kick", "free_kick": "Free kick", "kickoff": "Back underway"},
        "de": {"throw_in": "Einwurf", "goal_kick": "Abstoß", "free_kick": "Freistoß", "kickoff": "Weiter geht's"},
        "fr": {"throw_in": "Touche", "goal_kick": "Six mètres", "free_kick": "Coup franc", "kickoff": "On repart"},
    },
    "player_note": {
        "en": {
            "trait:rapid": "has real pace", "trait:quick_off_the_mark": "is quick off the mark", "trait:aerial_threat": "is dominant in the air",
            "trait:long_range": "can strike it from distance", "trait:set_piece_taker": "is the dead-ball specialist",
            "trait:press_resistant": "stays so calm under pressure", "trait:engine": "never stops running",
            "trait:two_footed": "is happy on either foot", "trait:tough_tackler": "is a tough tackler", "trait:visionary": "sees the pass early",
            "trait:dribbler": "loves to take a man on",
            "role:poacher": "lives on the last line", "role:target_forward": "is the target man up front",
            "role:playmaker": "pulls the strings in midfield", "role:ball_playing_cb": "starts the moves from the back",
            "role:sweeper_keeper": "sweeps up well behind the line", "role:inverted_winger": "cuts in from the wing",
            "role:box_to_box": "covers every blade of grass", "role:anchor": "screens the back line",
            "passes": "has completed {count_word} passes so far", "season": "has scored {goals_word} this season",
            "captain": "wears the armband", "veteran": "is the experienced head in this side",
            "youngster": "is one of the youngest on the pitch", "lefty": "is left-footed",
            "apps": "has played {count_word} games this season", "assists": "has set up {count_word} goals this season",
            "clean_sheets": "has kept {count_word} clean sheets this season", "tallest": "is the tallest outfield player out there",
        },
        "de": {
            "trait:rapid": "hat enormes Tempo", "trait:quick_off_the_mark": "ist sofort auf Touren", "trait:aerial_threat": "ist stark in der Luft",
            "trait:long_range": "schießt auch aus der Distanz", "trait:set_piece_taker": "ist der Standardspezialist",
            "trait:press_resistant": "bleibt unter Druck ganz ruhig", "trait:engine": "läuft unermüdlich",
            "trait:two_footed": "ist mit beiden Füßen stark", "trait:tough_tackler": "ist ein harter Zweikämpfer",
            "trait:visionary": "erkennt den Pass früh", "trait:dribbler": "geht gern ins Dribbling",
            "role:poacher": "lauert an der letzten Linie", "role:target_forward": "ist die Anspielstation vorn",
            "role:playmaker": "zieht im Mittelfeld die Fäden", "role:ball_playing_cb": "eröffnet das Spiel von hinten",
            "role:sweeper_keeper": "spielt weit vor dem Tor mit", "role:inverted_winger": "zieht vom Flügel nach innen",
            "role:box_to_box": "ist überall auf dem Platz", "role:anchor": "sichert vor der Abwehr ab",
            "passes": "hat bisher {count_word} Pässe an den Mann gebracht", "season": "hat in dieser Saison schon {goals_word} Tore erzielt",
            "captain": "trägt die Kapitänsbinde", "veteran": "ist der erfahrene Kopf dieser Mannschaft",
            "youngster": "gehört zu den Jüngsten auf dem Platz", "lefty": "ist Linksfuß",
            "apps": "hat in dieser Saison {count_word} Spiele bestritten", "assists": "hat in dieser Saison {count_word} Tore vorbereitet",
            "clean_sheets": "hat in dieser Saison schon {count_word} Mal die Null gehalten", "tallest": "ist der größte Feldspieler auf dem Platz",
        },
        "fr": {
            "trait:rapid": "a une vraie vitesse", "trait:quick_off_the_mark": "démarre très vite", "trait:aerial_threat": "est dominant dans les airs",
            "trait:long_range": "sait frapper de loin", "trait:set_piece_taker": "est le spécialiste des coups de pied arrêtés",
            "trait:press_resistant": "reste très calme sous la pression", "trait:engine": "ne s'arrête jamais de courir",
            "trait:two_footed": "est à l'aise des deux pieds", "trait:tough_tackler": "est un défenseur teigneux",
            "trait:visionary": "voit la passe très tôt", "trait:dribbler": "adore éliminer son vis-à-vis",
            "role:poacher": "vit sur la dernière ligne", "role:target_forward": "est le point d'appui devant",
            "role:playmaker": "dirige le jeu au milieu", "role:ball_playing_cb": "lance les actions depuis l'arrière",
            "role:sweeper_keeper": "joue haut devant sa surface", "role:inverted_winger": "repique dans l'axe depuis l'aile",
            "role:box_to_box": "couvre tout le terrain", "role:anchor": "protège la défense",
            "passes": "a réussi {count_word} passes jusqu'ici", "season": "a déjà marqué {goals_word} buts cette saison",
            "captain": "porte le brassard", "veteran": "est la tête d'expérience de cette équipe",
            "youngster": "fait partie des plus jeunes sur le terrain", "lefty": "est gaucher",
            "apps": "a disputé {count_word} matches cette saison", "assists": "a délivré {count_word} passes décisives cette saison",
            "clean_sheets": "a gardé sa cage inviolée {count_word} fois cette saison", "tallest": "est le plus grand joueur de champ sur le terrain",
        },
    },
    "shape_note": {
        "en": {"chase": "{team} have pushed the line right up", "protect": "{team} have dropped deep to protect what they have",
               "ten_men": "{team} are a man down and have tightened up"},
        "de": {"chase": "{team} hat die Abwehrkette weit nach vorn geschoben", "protect": "{team} zieht sich tief zurück, um das Ergebnis zu halten",
               "ten_men": "{team} hat einen Mann weniger und rückt enger zusammen"},
        "fr": {"chase": "{team} a relevé sa ligne d'un cran", "protect": "{team} s'est replié pour protéger son avance",
               "ten_men": "{team} est en infériorité et se resserre"},
    },
    "press_note": {
        "en": {"intense": "{team} are pressing high and in numbers", "passive": "{team} are happy to let the ball go"},
        "de": {"intense": "{team} presst hoch und mit vielen Leuten", "passive": "{team} presst kaum und lässt den Gegner kommen"},
        "fr": {"intense": "{team} presse haut et à plusieurs", "passive": "{team} laisse volontiers le ballon à l'adversaire"},
    },
    "tempo_note": {
        "en": {"slow": "{team} are in no hurry on the ball", "high": "{team} are playing at a real tempo",
               "slow_2": "{team} are keeping it slow and patient", "high_2": "{team} are moving the ball quickly now"},
        "de": {"slow": "{team} lässt sich Zeit am Ball", "high": "{team} spielt mit richtig Tempo",
               "slow_2": "{team} spielt ruhig und geduldig", "high_2": "{team} lässt den Ball jetzt schnell laufen"},
        "fr": {"slow": "{team} prend son temps avec le ballon", "high": "{team} joue à un vrai rythme",
               "slow_2": "{team} joue calmement et patiemment", "high_2": "{team} fait vite circuler le ballon"},
    },
    "counter_note": {
        "en": {"corners": "That is the {nth_word} corner in five minutes for {team}", "fouls": "That is {player}'s {nth_word} foul",
               "passes": "{team} have strung {n_word} passes together", "passes_2": "{team} have kept the ball for {n_word} passes now",
               "shots": "That is {team}'s {nth_word} shot of the match", "spell": "First touch for {player} in a long while",
               "move": "{chain_text} worked it, and {player} finished it off", "tally": "{player} now has {n_word} goals this season",
               "tally_first": "That is {player}'s first goal of the season",
               "goalless": "Still goalless after {n_word} minutes", "goalless_2": "Nothing between them after {n_word} minutes",
               "goalless_added": "Still goalless in added time",
               "level": "All square after {n_word} minutes", "level_2": "Still level after {n_word} minutes", "level_added": "All square in added time",
               "lead": "{team} lead after {n_word} minutes", "lead_2": "{team} are ahead after {n_word} minutes", "lead_added": "{team} lead in added time",
               "shots_total": "{team} have had {n_word} shots so far", "shots_total_2": "That is {n_word} shots now for {team}",
               "corners_total": "{team} have won {n_word} corners so far", "corners_total_2": "{team} are up to {n_word} corners now",
               "fouls_total": "{team} have given away {n_word} fouls", "fouls_total_2": "That makes {n_word} fouls for {team}",
               "possession": "{team} have had {n_word} percent of the ball so far", "possession_2": "{team} are seeing {n_word} percent of the ball",
               "crosses_total": "{team} have put in {n_word} crosses so far", "crosses_total_2": "That makes {n_word} crosses for {team}",
               "long_total": "{team} have gone long {n_word} times", "long_total_2": "That is {n_word} long balls now for {team}",
               "won_back_total": "{team} have won the ball back {n_word} times", "won_back_total_2": "That makes {n_word} turnovers won by {team}",
               "on_target_total": "{team} have had {n_word} shots on target", "on_target_total_2": "That is {n_word} on target now for {team}",
               "saves_total": "{team}'s keeper has made {n_word} saves", "saves_total_2": "That is {n_word} saves now for {team}'s keeper",
               "spell_end": "{N_word} passes there for {team} before play stopped",
               "throws_total": "{team} have taken {n_word} throw-ins so far", "throws_total_2": "That makes {n_word} throw-ins for {team}",
               "goal_kicks_total": "{team} have taken {n_word} goal kicks so far", "goal_kicks_total_2": "That is {n_word} goal kicks now for {team}",
               "recent_ball": "Over the last three minutes {team} have had {n_word} percent of the ball", "recent_ball_2": "{team} have seen {n_word} percent of the ball in the last three minutes",
               "drought": "{team} have not had a shot for {n_word} minutes", "drought_2": "No shot for {team} in the last {n_word} minutes",
               "chance_saved": "{player} has a go, but {keeper} is equal to it", "chance_off": "{player} has a go, but it is off target",
               "chance_blocked": "{player} has a go, but it is blocked", "chance_post": "{player} has a go and hits the post"},
        "de": {"corners": "Das ist die {nth_word} Ecke für {team} in fünf Minuten", "fouls": "Das ist das {nth_word} Foul von {player}",
               "passes": "{team} spielt {n_word} Pässe in Folge", "passes_2": "{team} hält den Ball jetzt schon {n_word} Pässe lang",
               "shots": "Das ist der {nth_word} Schuss von {team}", "spell": "Der erste Ballkontakt von {player} seit langer Zeit",
               "move": "{chain_text} kombinieren sich nach vorn, und {player} vollendet", "tally": "{player} steht jetzt bei {n_word} Saisontoren",
               "tally_first": "Das ist das erste Saisontor von {player}",
               "goalless": "Nach {n_word} Minuten ist es noch torlos", "goalless_2": "Noch kein Tor nach {n_word} Minuten",
               "goalless_added": "Noch immer torlos in der Nachspielzeit",
               "level": "Nach {n_word} Minuten steht es unentschieden", "level_2": "Gleichstand nach {n_word} Minuten", "level_added": "Gleichstand in der Nachspielzeit",
               "lead": "{team} führt nach {n_word} Minuten", "lead_2": "{team} liegt nach {n_word} Minuten vorn", "lead_added": "{team} führt in der Nachspielzeit",
               "shots_total": "{team} hat bisher {n_word} Torschüsse abgegeben", "shots_total_2": "Das sind jetzt {n_word} Schüsse für {team}",
               "corners_total": "{team} hat bisher {n_word} Ecken herausgeholt", "corners_total_2": "{team} steht jetzt bei {n_word} Ecken",
               "fouls_total": "{team} hat schon {n_word} Fouls begangen", "fouls_total_2": "Das macht {n_word} Fouls für {team}",
               "possession": "{team} hat bisher {n_word} Prozent Ballbesitz", "possession_2": "{team} kommt auf {n_word} Prozent Ballbesitz",
               "crosses_total": "{team} hat bisher {n_word} Flanken geschlagen", "crosses_total_2": "Das sind jetzt {n_word} Flanken für {team}",
               "long_total": "{team} hat es schon {n_word} Mal mit langen Bällen versucht", "long_total_2": "Schon {n_word} lange Bälle von {team}",
               "won_back_total": "{team} hat den Ball schon {n_word} Mal zurückerobert", "won_back_total_2": "Das macht {n_word} Ballgewinne für {team}",
               "on_target_total": "{team} hat {n_word} Schüsse aufs Tor gebracht", "on_target_total_2": "Das sind jetzt {n_word} Schüsse aufs Tor für {team}",
               "saves_total": "Der Torhüter von {team} hat schon {n_word} Mal gerettet", "saves_total_2": "Das sind {n_word} Paraden für den Torhüter von {team}",
               "spell_end": "{N_word} Pässe von {team}, dann wurde das Spiel unterbrochen",
               "throws_total": "{team} hat bisher {n_word} Einwürfe gehabt", "throws_total_2": "Das macht {n_word} Einwürfe für {team}",
               "goal_kicks_total": "{team} hat bisher {n_word} Abstöße ausgeführt", "goal_kicks_total_2": "Das sind jetzt {n_word} Abstöße für {team}",
               "recent_ball": "In den letzten drei Minuten hatte {team} {n_word} Prozent der Ballkontakte", "recent_ball_2": "{team} kommt in den letzten drei Minuten auf {n_word} Prozent Ballbesitz",
               "drought": "{team} hat seit {n_word} Minuten keinen Schuss mehr abgegeben", "drought_2": "Seit {n_word} Minuten kein Torschuss von {team}",
               "chance_saved": "{player} zieht ab, aber {keeper} ist zur Stelle", "chance_off": "{player} zieht ab, aber der Ball geht vorbei",
               "chance_blocked": "{player} zieht ab, aber der Schuss wird geblockt", "chance_post": "{player} zieht ab und trifft den Pfosten"},
        "fr": {"corners": "C'est le {nth_word} corner de {team} en cinq minutes", "fouls": "C'est la {nth_word} faute de {player}",
               "passes": "{team} enchaîne {n_word} passes", "passes_2": "{team} garde le ballon depuis {n_word} passes",
               "shots": "C'est le {nth_word} tir de {team}", "spell": "Premier ballon de {player} depuis longtemps",
               "move": "{chain_text} font tourner le ballon, et {player} conclut", "tally": "{player} en est à {n_word} buts cette saison",
               "tally_first": "C'est le premier but de {player} cette saison",
               "goalless": "Toujours pas de but après {n_word} minutes", "goalless_2": "Rien entre eux après {n_word} minutes",
               "goalless_added": "Toujours aucun but dans les arrêts de jeu",
               "level": "Égalité après {n_word} minutes", "level_2": "Toujours à égalité après {n_word} minutes", "level_added": "Égalité dans les arrêts de jeu",
               "lead": "{team} mène après {n_word} minutes", "lead_2": "{team} est devant après {n_word} minutes", "lead_added": "{team} mène dans les arrêts de jeu",
               "shots_total": "{team} a tenté {n_word} tirs jusqu'ici", "shots_total_2": "Cela fait {n_word} tirs pour {team}",
               "corners_total": "{team} a obtenu {n_word} corners jusqu'ici", "corners_total_2": "{team} en est à {n_word} corners",
               "fouls_total": "{team} a commis {n_word} fautes", "fouls_total_2": "Cela fait {n_word} fautes pour {team}",
               "possession": "{team} a eu {n_word} pour cent du ballon jusqu'ici", "possession_2": "{team} dispose de {n_word} pour cent du ballon",
               "crosses_total": "{team} a déjà centré {n_word} fois", "crosses_total_2": "Cela fait {n_word} centres pour {team}",
               "long_total": "{team} a tenté {n_word} longs ballons", "long_total_2": "Cela fait {n_word} longs ballons pour {team}",
               "won_back_total": "{team} a récupéré le ballon {n_word} fois", "won_back_total_2": "Cela fait {n_word} ballons récupérés par {team}",
               "on_target_total": "{team} a cadré {n_word} tirs", "on_target_total_2": "Cela fait {n_word} tirs cadrés pour {team}",
               "saves_total": "Le gardien de {team} a déjà fait {n_word} arrêts", "saves_total_2": "Cela fait {n_word} arrêts pour le gardien de {team}",
               "spell_end": "{N_word} passes de {team}, puis le jeu s'arrête",
               "throws_total": "{team} a déjà eu {n_word} touches", "throws_total_2": "Cela fait {n_word} touches pour {team}",
               "goal_kicks_total": "{team} a déjà dégagé {n_word} fois depuis les six mètres", "goal_kicks_total_2": "Cela fait {n_word} dégagements aux six mètres pour {team}",
               "recent_ball": "Sur les trois dernières minutes, {team} a eu {n_word} pour cent du ballon", "recent_ball_2": "{team} a vu {n_word} pour cent du ballon ces trois dernières minutes",
               "drought": "{team} n'a pas tiré depuis {n_word} minutes", "drought_2": "Pas de tir pour {team} depuis {n_word} minutes",
               "chance_saved": "{player} tente sa chance, mais {keeper} veille", "chance_off": "{player} tente sa chance, mais le ballon passe à côté",
               "chance_blocked": "{player} tente sa chance, mais la frappe est contrée", "chance_post": "{player} tente sa chance et touche le poteau"},
    },
    # the longer sentence of a dead ball (`{note_long}`): only facts the builder holds, one clause more than `note`. A facet without an entry here
    # (or with an entry that needs a fact the moment lacks, like `assist`) has no long wording; `_2` facets use the entry of their base facet
    "counter_note_long": {
        "en": {"move": "After a move through {chain_text}, {player} finishes it off to make it {score_words}",
               "corners": "That is the {nth_word} corner in five minutes for {team}, who now have {sh_shots} in the match",
               "shots": "That is {team}'s {nth_word} shot of the match, and {other} have had {so_word} of their own",
               "fouls": "That is {player}'s {nth_word} foul, and {team} have given away {m_word} fouls in all",
               "passes": "{team} have strung {n_word} passes together without losing it, and {other} have not had a touch",
               "tally": "{player} now has {n_word} goals this season, and this one was set up by {assist}",
               "tally_first": "That is {player}'s first goal of the season, and {assist} set it up",
               "goalless": "Still goalless after {n_word} minutes, and neither side has found a way through",
               "goalless_added": "Still goalless in added time, and neither side has found a way through",
               "level": "All square after {n_word} minutes, with the shots at {sh_word} for {team} and {so_word} for {other}",
               "level_added": "All square in added time, with the shots at {sh_word} for {team} and {so_word} for {other}",
               "lead": "{team} lead after {n_word} minutes, and {other} are still looking for an answer",
               "lead_added": "{team} lead in added time, and {other} are running out of time to find an answer",
               "shots_total": "{team} have had {n_word} shots so far, and {other} have had {m_word} of their own",
               "corners_total": "{team} have won {n_word} corners so far, and {other} have won {m_word} of their own",
               "fouls_total": "{team} have given away {n_word} fouls, and {other} have given away {m_word} of their own",
               "possession": "{team} have had {n_word} percent of the ball so far, which leaves {other} with {m_word}",
               "crosses_total": "{team} have put in {n_word} crosses so far, and {other} have put in {m_word} of their own",
               "long_total": "{team} have gone long {n_word} times so far, and {other} have gone long {m_times}",
               "won_back_total": "{team} have won the ball back {n_word} times, and {other} have won it back {m_times}",
               "on_target_total": "{team} have had {n_word} shots on target, and {other} have had {m_word} of their own",
               "saves_total": "{team}'s keeper has made {n_word} saves, while the keeper of {other} has made {m_word}",
               "spell_end": "That was a move of {n_word} passes from {team} before play stopped, and {other} never got a touch",
               "throws_total": "{team} have taken {n_word} throw-ins so far, and {other} have taken {m_word} of their own",
               "goal_kicks_total": "{team} have taken {n_word} goal kicks so far, and {other} have taken {m_word} of their own",
               "recent_ball": "Over the last three minutes {team} have had {n_word} percent of the ball, which leaves {other} with {m_word} percent",
               "drought": "{team} have not had a shot for {n_word} minutes, and {other} have had {m_word} in that time",
               "chance_saved": "After a move through {chain_text}, {player} has a go, but {keeper} is equal to it",
               "chance_off": "After a move through {chain_text}, {player} has a go, but it goes wide of the target",
               "chance_blocked": "After a move through {chain_text}, {player} has a go, but it is blocked on the way",
               "chance_post": "After a move through {chain_text}, {player} has a go and hits the post"},
        "de": {"move": "Nach dem Spielzug über {chain_text} vollendet {player}, und es steht {score_words}",
               "corners": "Das ist die {nth_word} Ecke für {team} in fünf Minuten, und {team} hat damit {sh_word} Torschüsse in dieser Partie",
               "shots": "Das ist der {nth_word} Schuss von {team} in diesem Spiel, und {other} hat bisher {so_word} abgegeben",
               "fouls": "Das ist das {nth_word} Foul von {player}, und {team} hat insgesamt schon {m_word} Fouls begangen",
               "passes": "{team} spielt {n_word} Pässe in Folge, ohne den Ball zu verlieren, und {other} kommt nicht an den Ball",
               "tally": "{player} steht jetzt bei {n_word} Saisontoren, und dieses Tor hat {assist} vorbereitet",
               "tally_first": "Das ist das erste Saisontor von {player}, und {assist} hat es vorbereitet",
               "goalless": "Nach {n_word} Minuten ist es noch torlos, und noch hat keine Seite einen Weg gefunden",
               "goalless_added": "Noch immer torlos in der Nachspielzeit, und noch hat keine Seite einen Weg gefunden",
               "level": "Nach {n_word} Minuten steht es unentschieden, und bei den Schüssen kommt {team} auf {sh_word} und {other} auf {so_word}",
               "level_added": "Gleichstand in der Nachspielzeit, und bei den Schüssen kommt {team} auf {sh_word} und {other} auf {so_word}",
               "lead": "{team} führt nach {n_word} Minuten, und {other} sucht noch immer eine passende Antwort",
               "lead_added": "{team} führt in der Nachspielzeit, und {other} läuft jetzt langsam die Zeit davon",
               "shots_total": "{team} hat bisher {n_word} Torschüsse abgegeben, und {other} kommt in dieser Partie auf {m_word}",
               "corners_total": "{team} hat bisher {n_word} Ecken herausgeholt, und {other} kommt in dieser Partie auf {m_word}",
               "fouls_total": "{team} hat schon {n_word} Fouls begangen, und {other} kommt in dieser Partie auf {m_word}",
               "possession": "{team} hat bisher {n_word} Prozent Ballbesitz, damit bleiben für {other} noch {m_word} Prozent",
               "crosses_total": "{team} hat bisher {n_word} Flanken geschlagen, während {other} bislang auf {m_word} kommt",
               "long_total": "{team} hat es schon {n_word} Mal mit langen Bällen versucht, während {other} auf {m_word} kommt",
               "won_back_total": "{team} hat den Ball schon {n_word} Mal zurückerobert, während {other} auf {m_word} kommt",
               "on_target_total": "{team} hat {n_word} Schüsse aufs Tor gebracht, während {other} auf {m_word} kommt",
               "saves_total": "Der Torhüter von {team} hat schon {n_word} Mal gerettet, während der von {other} auf {m_word} kommt",
               "spell_end": "Das war ein Angriff mit {n_word} Pässen von {team}, bevor das Spiel unterbrochen wurde, ohne dass {other} an den Ball kam",
               "throws_total": "{team} hat bisher {n_word} Einwürfe gehabt, während {other} in dieser Partie auf {m_word} kommt",
               "goal_kicks_total": "{team} hat bisher {n_word} Abstöße ausgeführt, während {other} in dieser Partie auf {m_word} kommt",
               "recent_ball": "In den letzten drei Minuten hatte {team} {n_word} Prozent der Ballkontakte, damit bleiben für {other} nur {m_word} Prozent",
               "drought": "{team} hat seit {n_word} Minuten keinen Schuss mehr abgegeben, während {other} in dieser Zeit auf {m_word} kam",
               "chance_saved": "Nach dem Spielzug über {chain_text} zieht {player} ab, aber {keeper} ist zur Stelle",
               "chance_off": "Nach dem Spielzug über {chain_text} zieht {player} ab, aber der Ball geht vorbei",
               "chance_blocked": "Nach dem Spielzug über {chain_text} zieht {player} ab, aber der Schuss wird geblockt",
               "chance_post": "Nach dem Spielzug über {chain_text} zieht {player} ab und trifft den Pfosten"},
        "fr": {"move": "Après un mouvement passé par {chain_text}, {player} conclut, et c'est {score_words}",
               "corners": "C'est le {nth_word} corner de {team} en cinq minutes, et {team} compte maintenant {sh_word} tirs dans ce match",
               "shots": "C'est le {nth_word} tir de {team} dans ce match, et {other} en est à {so_word} de son côté",
               "fouls": "C'est la {nth_word} faute de {player}, et {team} a commis {m_word} fautes en tout",
               "passes": "{team} enchaîne {n_word} passes sans perdre le ballon, et {other} n'a pas touché la balle",
               "tally": "{player} en est à {n_word} buts cette saison, et c'est {assist} qui a préparé celui-ci",
               "tally_first": "C'est le premier but de {player} cette saison, et c'est {assist} qui l'a préparé",
               "goalless": "Toujours pas de but après {n_word} minutes, et aucune des deux équipes n'a trouvé la faille",
               "goalless_added": "Toujours aucun but dans les arrêts de jeu, et aucune des deux équipes n'a trouvé la faille",
               "level": "Égalité après {n_word} minutes, et côté tirs, {team} en est à {sh_word} et {other} à {so_word}",
               "level_added": "Égalité dans les arrêts de jeu, et côté tirs, {team} en est à {sh_word} et {other} à {so_word}",
               "lead": "{team} mène après {n_word} minutes, et {other} est toujours à la recherche d'une réponse",
               "lead_added": "{team} mène dans les arrêts de jeu, et {other} manque de temps pour répondre",
               "shots_total": "{team} a tenté {n_word} tirs jusqu'ici, et {other} en est à {m_word} de son côté",
               "corners_total": "{team} a obtenu {n_word} corners jusqu'ici, et {other} en est à {m_word} de son côté",
               "fouls_total": "{team} a commis {n_word} fautes, et {other} en est à {m_word} de son côté",
               "possession": "{team} a eu {n_word} pour cent du ballon jusqu'ici, ce qui laisse {m_word} pour cent à {other}",
               "crosses_total": "{team} a déjà centré {n_word} fois, alors que {other} en est à {m_word} de son côté",
               "long_total": "{team} a tenté {n_word} longs ballons, alors que {other} en est à {m_word} de son côté",
               "won_back_total": "{team} a récupéré le ballon {n_word} fois, alors que {other} l'a fait {m_word} fois",
               "on_target_total": "{team} a cadré {n_word} tirs, alors que {other} en a cadré {m_word} de son côté",
               "saves_total": "Le gardien de {team} a déjà fait {n_word} arrêts, alors que celui de {other} en a fait {m_word}",
               "spell_end": "C'était un enchaînement de {n_word} passes de {team} avant l'arrêt du jeu, sans que {other} touche le ballon",
               "throws_total": "{team} a déjà eu {n_word} touches, alors que {other} en est à {m_word} de son côté",
               "goal_kicks_total": "{team} a déjà dégagé {n_word} fois depuis les six mètres, alors que {other} en est à {m_word} de son côté",
               "recent_ball": "Sur les trois dernières minutes, {team} a eu {n_word} pour cent du ballon, ce qui laisse {m_word} pour cent à {other}",
               "drought": "{team} n'a pas tiré depuis {n_word} minutes, alors que {other} en a tenté {m_word} pendant ce temps",
               "chance_saved": "Après un mouvement passé par {chain_text}, {player} tente sa chance, mais {keeper} veille",
               "chance_off": "Après un mouvement passé par {chain_text}, {player} tente sa chance, mais le ballon passe à côté",
               "chance_blocked": "Après un mouvement passé par {chain_text}, {player} tente sa chance, mais la frappe est contrée",
               "chance_post": "Après un mouvement passé par {chain_text}, {player} tente sa chance et touche le poteau"},
    },
    "tempo_note_long": {
        "en": {"slow": "{team} are in no hurry on the ball, and have been that way for the last few minutes",
               "high": "{team} are playing at a real tempo, and have been for the last few minutes"},
        "de": {"slow": "{team} lässt sich Zeit am Ball, und das schon seit ein paar Minuten",
               "high": "{team} spielt mit richtig Tempo, und das schon seit ein paar Minuten"},
        "fr": {"slow": "{team} prend son temps avec le ballon, et cela depuis quelques minutes",
               "high": "{team} joue à un vrai rythme, et cela depuis quelques minutes"},
    },
    "story_note": {
        "en": {
            "table": "{team} came into this one {place_word} in the table, on {n_word} points",
            "form": "{team} have won {n_word} of their last five, and lost {m_word}",
            "form_one": "{team} have won just one of their last five, and lost {m_word}",
            "form_winless": "{team} are without a win in their last five",
            "coach": "{coach} is in year {n_word} in charge of {team}",
            "coach_new": "{coach} is in a first season in charge of {team}",
            "comebacks": "{team} have already come from behind to take points {n_word} times this season",
            "comebacks_once": "{team} have come from behind to take points once already this season",
            "home_run": "{team} are unbeaten in {n_word} home games here at {venue}",
            "last_meeting": "Last season this fixture finished {score_words}, and {player} scored that day",
            "last_meeting_0": "Last season this fixture finished {score_words}",
            "former_club": "{player} joined {team} from {club} {n_word} years ago",
            "former_club_1": "{player} only joined {team} from {club} last year",
            "milestone": "This is appearance number {count_word} for {player} in a {team} shirt",
            "academy": "{player} came through the {team} academy, and is only {n_word}",
            "debut": "A first appearance of the season for {player} today",
        },
        "de": {
            "table": "{team} geht auf Platz {place_n} der Tabelle in dieses Spiel, mit {n_word} Punkten",
            "form": "{team} hat {n_word} der letzten fünf Spiele gewonnen und {m_word} verloren",
            "form_one": "{team} hat nur eines der letzten fünf Spiele gewonnen und {m_word} verloren",
            "form_winless": "{team} wartet seit fünf Spielen auf einen Sieg",
            "coach": "{coach} ist seit {n_word} Jahren Trainer bei {team}",
            "coach_new": "{coach} ist in der ersten Saison Trainer bei {team}",
            "comebacks": "{team} hat in dieser Saison schon {n_word} Mal nach Rückstand gepunktet",
            "comebacks_once": "{team} hat in dieser Saison schon einmal nach Rückstand gepunktet",
            "home_run": "{team} ist seit {n_word} Heimspielen hier im {venue} ungeschlagen",
            "last_meeting": "In der letzten Saison endete dieses Duell {score_words}, und {player} hat damals getroffen",
            "last_meeting_0": "In der letzten Saison endete dieses Duell {score_words}",
            "former_club": "{player} kam vor {n_word} Jahren von {club} zu {team}",
            "former_club_1": "{player} kam erst letztes Jahr von {club} zu {team}",
            "milestone": "Für {player} ist das heute Einsatz Nummer {count_word} im Trikot von {team}",
            "academy": "{player} kommt aus der eigenen Jugend von {team} und ist erst {n_word}",
            "debut": "Für {player} ist es heute der erste Einsatz der Saison",
        },
        "fr": {
            "table": "{team} aborde ce match à la {place_word} place, avec {n_word} points",
            "form": "{team} a gagné {n_word} de ses cinq derniers matchs, pour {m_word} défaites",
            "form_one": "{team} n'a gagné qu'un seul de ses cinq derniers matchs, pour {m_word} défaites",
            "form_winless": "{team} n'a plus gagné depuis cinq matchs",
            "coach": "{coach} est à la tête de {team} depuis {n_word} ans",
            "coach_new": "{coach} vit sa première saison à la tête de {team}",
            "comebacks": "{team} a déjà pris des points après avoir été mené {n_word} fois cette saison",
            "comebacks_once": "{team} a déjà pris des points après avoir été mené une fois cette saison",
            "home_run": "{team} reste sur {n_word} matchs sans défaite ici, à {venue}",
            "last_meeting": "La saison dernière, ce match s'était terminé sur le score de {score_words}, avec un but de {player}",
            "last_meeting_0": "La saison dernière, ce match s'était terminé sur le score de {score_words}",
            "former_club": "{player} est arrivé {de_club} voilà {n_word} ans",
            "former_club_1": "{player} n'est arrivé {de_club} que l'an dernier",
            "milestone": "C'est le match numéro {count_word} de {player} sous le maillot de {team}",
            "academy": "{player} est un pur produit du centre de formation de {team}, à seulement {n_word} ans",
            "debut": "Première apparition de la saison pour {player} aujourd'hui",
        },
    },
    "story_note_bare": {
        "en": {
            "table": "{team} started the day {place_word} in the league table, with {n_word} points so far",
            "form": "{team} come into this having won {n_word} of their last five league games",
            "form_one": "{team} come into this having won just one of their last five league games",
            "form_winless": "{team} have not won any of their last five league games, so confidence could be low",
            "coach": "The coach of {team}, {coach}, has been in the job for {n_word} years now",
            "coach_new": "{team} have a new coach this season, {coach}",
            "comebacks": "Do not write {team} off yet, they have come from behind to take points {n_word} times this season",
            "comebacks_once": "Do not write {team} off yet, they have come from behind to take points once already this season",
            "home_run": "{team} like it here, they have not lost any of their last {n_word} home games",
            "last_meeting": "When these two met last season it ended {score_words}, and {player} was one of the scorers",
            "last_meeting_0": "When these two met last season it ended {score_words}",
            "former_club": "{player} used to play for {club}, and moved to {team} {n_word} years ago",
            "former_club_1": "{player} is fairly new here, signed from {club} only last year",
            "milestone": "A special day for {player}, who plays game number {count_word} for {team}",
            "academy": "{player} grew up at this club, through its youth teams, and is just {n_word}",
            "debut": "{player} has not played yet this season, so this is a first game for a while",
        },
        "de": {
            "table": "{team} steht vor dem Spiel auf Platz {place_n} der Tabelle, mit {n_word} Punkten",
            "form": "{team} hat {n_word} der letzten fünf Ligaspiele gewonnen",
            "form_one": "{team} hat nur eines der letzten fünf Ligaspiele gewonnen",
            "form_winless": "{team} hat keines der letzten fünf Ligaspiele gewonnen, das Selbstvertrauen dürfte fehlen",
            "coach": "Der Trainer von {team}, {coach}, ist schon {n_word} Jahre im Amt",
            "coach_new": "{team} hat in dieser Saison einen neuen Trainer, {coach}",
            "comebacks": "{team} sollte man nicht abschreiben, die Mannschaft hat schon {n_word} Mal nach Rückstand gepunktet",
            "comebacks_once": "{team} sollte man nicht abschreiben, die Mannschaft hat schon einmal nach Rückstand gepunktet",
            "home_run": "{team} fühlt sich hier wohl und hat die letzten {n_word} Heimspiele nicht verloren",
            "last_meeting": "Beim letzten Duell der beiden stand es am Ende {score_words}, und {player} hat getroffen",
            "last_meeting_0": "Beim letzten Duell der beiden stand es am Ende {score_words}",
            "former_club": "{player} hat früher bei {club} gespielt und ist seit {n_word} Jahren bei {team}",
            "former_club_1": "{player} ist noch recht neu hier, erst letztes Jahr von {club} gekommen",
            "milestone": "Ein besonderer Tag für {player}, heute ist es Spiel Nummer {count_word} für {team}",
            "academy": "{player} ist hier im Verein groß geworden, in der eigenen Jugend, und ist erst {n_word}",
            "debut": "{player} hat in dieser Saison noch nicht gespielt, heute ist das erste Spiel",
        },
        "fr": {
            "table": "{team} a commencé la journée à la {place_word} place du classement, avec {n_word} points",
            "form": "{team} arrive avec {n_word} victoires lors de ses cinq derniers matchs de championnat",
            "form_one": "{team} n'a gagné qu'un seul de ses cinq derniers matchs de championnat",
            "form_winless": "{team} n'a gagné aucun de ses cinq derniers matchs, la confiance peut manquer",
            "coach": "L'entraîneur de {team}, {coach}, est en poste depuis {n_word} ans",
            "coach_new": "{team} a un nouvel entraîneur cette saison, {coach}",
            "comebacks": "Attention à {team}, qui a déjà pris des points {n_word} fois cette saison après avoir été mené",
            "comebacks_once": "Attention à {team}, qui a déjà pris des points une fois cette saison après avoir été mené",
            "home_run": "{team} se sent bien ici, aucune défaite lors des {n_word} derniers matchs à domicile",
            "last_meeting": "La dernière fois, ce match s'était terminé sur le score de {score_words}, et {player} avait marqué",
            "last_meeting_0": "La dernière fois, ce match s'était terminé sur le score de {score_words}",
            "former_club": "{player} jouait avant à {club}, et porte le maillot de {team} depuis {n_word} ans",
            "former_club_1": "{player} est encore nouveau ici, arrivé {de_club} l'an dernier",
            "milestone": "Un jour spécial pour {player}, qui dispute le match numéro {count_word} avec {team}",
            "academy": "{player} a grandi dans ce club, dans ses équipes de jeunes, et n'a que {n_word} ans",
            "debut": "{player} n'avait pas encore joué cette saison, c'est un premier match",
        },
    },
    "phase_note": {
        "en": {"high": "{team} are defending high up the pitch", "low": "{team} sit in a low block and wait for the turnover",
               "counter": "{team} are set up to break at speed"},
        "de": {"high": "{team} verteidigt hoch im Feld", "low": "{team} steht tief und wartet auf den Ballgewinn",
               "counter": "{team} lauert auf den schnellen Konter"},
        "fr": {"high": "{team} défend très haut sur le terrain", "low": "{team} attend bas, en bloc, de récupérer le ballon",
               "counter": "{team} est prêt à jaillir en contre"},
    },
}

for _langs in T.values():  # the director relies on short-to-long order
    for _styles in _langs.values():
        for _vs in _styles.values():
            _vs.sort(key=len)


def variants(kind: str, lang: str, style: str) -> list[str]:
    return list(T[kind][lang][style])
