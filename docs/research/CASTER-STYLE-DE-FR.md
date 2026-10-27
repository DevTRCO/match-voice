# How German and French TV commentators really call it

Paper only. Nothing in the code, prompts, templates or data was changed for this note. It describes how a real broadcast booth sounds in
German (Sky, DAZN, ARD/ZDF Sportschau) and French (Canal+, beIN Sports, TF1), so the de and fr channels can be judged against it.
All examples use our fictional clubs and players (Wexmoor Athletic, Tamsworth Wanderers; Ibsen, Rasmussen, Tavares, Fontaine).

Scenario used throughout: 70th minute, Wexmoor trail 0-1 at home. Ibsen intercepts, Rasmussen takes it on the chest, long ball to Tavares,
Tavares lays it off, Fontaine scores the equaliser in the 71st minute.

## 1. The short version

1. **The caller describes what you see, the expert explains why it happened.** Neither of them ever reports a model output. "Die Siegchance
   steigt auf 36 Prozent" is a data readout, not commentary. No German or French commentator says it.
2. **A build-up is names, not sentences.** One name per touch, maybe a verb. The sentence comes after the ball is in the net.
3. **A goal call has three beats:** the shout (name, name again, the word for goal or equaliser), a breath where the stadium is heard, then one
   full sentence that puts the goal into the story (minute, comeback, sub, first goal).
4. **The expert speaks after the replay starts, about a concrete picture:** the ball loss, the defender who did not follow, the touch, the
   substitution. Then, at most, one sentence about what it does to the match, in football idiom, not in probability.
5. **Numbers in speech are the score, the minute, a tally, the time left.** Percentages, win probability, xG, metres per second: never in a
   live call.

## 2. The booth and its timing

| Beat | Who | German | French | Length |
| --- | --- | --- | --- | --- |
| Build-up | caller | name chain, present tense, verbs only when the touch is special | name chain, often with "pour", "oui", "attention" | 1 to 4 words per touch |
| Shot | caller | "Fontaine!" rising, often "zieht ab", "schießt" | "Fontaine... frappe !" | 1 to 3 words |
| Goal call | caller | "Tooor!" or "Und da ist der Ausgleich!", name twice, score in words | "BUT !" (one long vowel or repeated), name twice, "égalisation" | 2 to 4 s of shouting |
| Breath | nobody | 2 to 4 s of crowd, sometimes longer on a big goal | same, French callers often keep shouting a little longer | 2 to 5 s |
| Summary | caller | one sentence of story: "der eingewechselte Fontaine", "in der 71. Minute", "Wexmoor ist zurück" | "Et Wexmoor est revenu !", "le match est relancé" | 8 to 20 words |
| Replay | expert | "Schau dir das an...", "Da musst du...", what went right or wrong, concrete | "Regardez...", "Il faut voir...", "Là, il y a un trou..." | 1 to 3 sentences, 10 to 25 words each |
| Back to play | caller | the time left and the task: "Noch knapp zwanzig Minuten." | "Il reste vingt minutes." | one short sentence |

The expert is addressed by first name by the caller ("Was sagst du, Jonas?", "Et toi, Karim ?"). The expert never opens with an
exclamation of his own while the caller is still shouting. This matches what `PROMPT_VERSION` v4 already asks of the colour analyst.

## 3. German

### 3.1 Goal calls

Real formulas (all short, all in common use):

- "Tooor!" (one long vowel on TV; "Tor, Tor, Tor!" is the radio and old Sportschau style).
- "Und da ist der Ausgleich!" / "Da ist er, der Ausgleich!" / "Der Ausgleich!"
- "Fontaine! Fontaine!" (name twice, the second louder or slower).
- "Und der ist drin!" / "Den macht er!" / "Drin!"
- "Eins zu eins!" (the score in words, said, not read off a graphic).
- On a sub who scores: "Der Joker sticht!" (real, very common idiom).
- On a comeback: "Wexmoor ist zurück!" / "Alles wieder offen!" / "Hier ist wieder alles drin!"
- Disbelief: "Das gibt's doch nicht!" / "Ist das zu fassen!" (used sparingly; "Unfassbar!" is the stronger form).

Written score: German writes **1:1**, never "1-1". The bank currently writes "es steht 1-1". In speech it is "eins zu eins".

### 3.2 How touches and passes are described

| Action | Typical German | Avoid |
| --- | --- | --- |
| Interception | "Ibsen geht dazwischen", "Ibsen fängt ihn ab", "Ballgewinn Ibsen" | "Abgefangen von Ibsen" (passive, reads like a ticker) |
| Chest control | "Rasmussen nimmt ihn mit der Brust an", "mit der Brust runter" | "Brustannahme." alone (a noun is a caption, not speech) |
| Long ball | "Rasmussen lang auf Tavares", "der lange Ball auf Tavares" | "Lang geschlagen auf Tavares" (half a construction) |
| Switch | "Verlagerung auf rechts", "rüber auf die andere Seite" | "Seitenwechsel" (that is the half-time change of ends) |
| Lay-off | "Tavares legt ab", "legt quer", "lässt prallen" | "passt zurück zu" |
| Through ball | "steckt durch", "der Steckpass", "in die Tiefe" | "spielt durch die Lücke" |
| Chip | "chippt", "lupft", "Lupfer" | "hebt den Ball" |
| Cross | "flankt", "Flanke", "bringt ihn rein", "scharf vors Tor" | "liefert eine Flanke" |
| Shot | "zieht ab", "schließt ab", "Abschluss", "aus der Drehung", "mit links" | "feuert" (only for a real blast) |
| Finish | "schiebt ein", "drückt ihn über die Linie", "flach ins Eck", "unter die Latte" | "findet das Netz", "begräbt ihn" (English calques) |

The chain itself: "Ibsen geht dazwischen... Rasmussen... lang auf Tavares... Tavares legt ab... Fontaine... Tooor!" Present tense, no
articles before names, the preposition "auf" carries the pass ("auf Tavares", "weiter auf Fontaine").

### 3.3 The caller right after the goal

One full sentence with story, not stats: "Der eingewechselte Fontaine, keine zehn Minuten auf dem Platz, und Wexmoor ist wieder da."
Typical frames: "Das hatte sich angedeutet." / "Und das ist hochverdient." / "Moral bewiesen von Wexmoor." / "Jetzt ist hier richtig was los."
/ "Das Spiel ist wieder offen." / "Und jetzt? Noch zwanzig Minuten."

### 3.4 The Experte

German experts (Sky and DAZN pundits, ARD/ZDF experts) speak in the generic "du", in fragments, often colloquial:

- Cause, concrete: "Der Ballverlust im Mittelfeld, der tut weh." / "Da fehlt die Zuordnung." / "Da musst du als Innenverteidiger mitgehen."
  / "Viel zu einfach, wie der Ball da durchrutscht."
- Praise of the touch: "Wie er den mit der Brust mitnimmt, das ist schon stark." / "Tavares mit dem Auge, legt ihn perfekt in den Lauf."
- What it means, in idiom: "Tamsworth hat sich zu weit zurückgezogen, das rächt sich jetzt." / "Jetzt kippt das Spiel." / "Jetzt hat Wexmoor
  Oberwasser." / "Die Wechsel haben gegriffen."
- Openers: "Ganz ehrlich...", "Für mich...", "Ich sag mal so...", "Schau dir das an...", "Und das ist genau das, was ich vorhin meinte."

What a German Experte does not say: "glaubt wieder an den Sieg" as an analysis (a caller might say "Wexmoor glaubt wieder dran", one clause, as
colour), "die Siegchance", "das verändert das Gefühl des Spiels", any percentage.

### 3.5 Beginner vs expert register

German TV has no beginner channel, but the gap between a Länderspiel on ARD/ZDF (general audience) and a Bundesliga game on Sky or DAZN
(regular fans) is the right model.

| | Beginner (ARD/ZDF prime time) | Expert (Sky, DAZN) |
| --- | --- | --- |
| Vocabulary | Flanke, Pass, Abschluss, Ausgleich, eingewechselt | Halbraum, Umschaltmoment, Restverteidigung, zweite Bälle, Kette, tiefe Läufe, Gegenpressing |
| Explaining | says why it matters ("Damit ist alles wieder offen"), never explains rules mid-play | assumes the stakes, explains the mechanism ("die Kette rückt nicht raus") |
| Names | full name on first mention, club named more often | surname only, nicknames for regulars |
| Tempo | a little slower, more full sentences | denser, more fragments |

Both registers shout the same goal call. The difference is the sentence after it.

### 3.6 Calques to avoid (German)

| Sounds translated | Real German |
| --- | --- |
| findet das Netz / begräbt ihn | trifft, macht ihn rein, schiebt ein |
| das verändert das ganze Gefühl des Spiels | jetzt kippt das Spiel, jetzt ist alles offen |
| Tamsworth muss von vorne anfangen | für Tamsworth geht es wieder bei null los (or: Tamsworth muss jetzt wieder kommen) |
| ein Spiel der zwei Hälften | zwei völlig verschiedene Halbzeiten |
| hat eine große Gelegenheit | hat die große Chance, die Riesenchance |
| er liefert eine Flanke | er bringt die Flanke |
| er hält ein sauberes Blatt | zu null spielen, ohne Gegentor |
| hinterer Pfosten | langer Pfosten (vorderer Pfosten = kurzer Pfosten) |
| Momentum in every line | once at most; "Wexmoor hat jetzt Oberwasser", "der Druck wird größer" |
| Siegchance, Wahrscheinlichkeit | not said at all |

## 4. French

### 4.1 Goal calls

Real formulas:

- "BUUUT !" (one long vowel) or "But ! But ! But !" (radio, RMC style; TV callers repeat less).
- "BUT de Fontaine !" / "Et c'est Fontaine !" / "Fontaine ! Fontaine !"
- "Égalisation !" / "Wexmoor égalise !" / "C'est l'égalisation !"
- "Un partout !" (the spoken score for 1-1; "un à un" is rare in speech, "un but partout" also common).
- "Quel but !" / "Oh la la !" / "Il l'a fait !" / "Au fond !" / "Et ça rentre !"
- Repetition of an exclamation is a documented feature of French live commentary: "quelle occasion, quelle occasion" (Acerenza 2013, below).
- On a comeback: "Le match est relancé !" / "Tout est relancé !" / "On a un match !" (very TV French).
- For the side that led: "Tout est à refaire pour Tamsworth." (the real idiom; "tout reprendre à zéro" is understood but flat).

Written score: "1-1" is fine in French captions.

### 4.2 How touches and passes are described

| Action | Typical French | Avoid |
| --- | --- | --- |
| Interception | "Ibsen intercepte", "Ibsen coupe la trajectoire", "bien vu Ibsen" | "Intercepté par Ibsen" (passive, ticker style) |
| Chest control | "contrôle de la poitrine Rasmussen", "Rasmussen, amorti poitrine" | "Amorti de la poitrine." without a name |
| Long ball | "le jeu long pour Tavares", "ballon long de Rasmussen" | "Long ballon vers Tavares" ("vers" is a map direction, callers say "pour") |
| Switch | "changement d'aile", "transversale de Rasmussen" | "switch" |
| Lay-off | "Tavares remet", "remise en retrait", "il remise pour Fontaine" | "il passe en arrière à" |
| Through ball | "en profondeur", "dans l'intervalle", "ballon dans le dos de la défense" | "à travers la défense" |
| Chip | "il pique son ballon", "la louche", "il le lobe" | "il chippe" (franglais) |
| Cross | "centre", "centre en retrait", "au premier poteau", "au second poteau" | "poteau arrière" (calque of back post) |
| Shot | "il frappe !", "frappe du droit", "plat du pied", "il enroule", "il croise" | "il tire un coup" |
| Finish | "au fond des filets", "petit filet", "sous la barre", "lucarne", "il ne tremble pas" | "il trouve le filet", "il enterre" (calques) |

The chain: "Ibsen intercepte... Rasmussen, poitrine... le jeu long pour Tavares... Tavares remet... Fontaine... frappe... BUT !" French
callers put small words in the gaps ("oui", "attention", "allez", "pour") where a German caller puts nothing.

### 4.3 The caller right after the goal

"Et Fontaine, entré il y a dix minutes, remet Wexmoor dans le match !" Typical frames: "Coaching gagnant !" (real phrase for a successful
sub) / "Wexmoor est revenu !" / "Le match est relancé." / "Il reste vingt minutes, et tout est possible."

### 4.4 The consultant

French consultants (Canal+, beIN, TF1) speak with "on", "là", "regardez", and a strong opinion:

- Cause, concrete: "Regardez, il y a un trou énorme entre les deux centraux." / "Il faut être plus agressif sur le porteur." / "Tamsworth
  perd ce ballon au milieu, et derrière on est en infériorité."
- Praise: "Le contrôle de Rasmussen, il faut le voir, c'est propre." / "La remise de Tavares, en une touche, parfaite."
- What it means, in idiom: "Tamsworth a reculé, a voulu gérer, et ça se paie." / "Là, Wexmoor a un temps fort." / "Le coaching est gagnant."
- Openers: "Franchement...", "Moi, ce qui me plaît...", "C'est ce que je disais tout à l'heure...", "Attention...".

What a French consultant does not say: "ses chances de gagner grimpent à 36 %", "Wexmoor reprend confiance" as the whole analysis (it is a
caller's colour clause), any percentage or probability.

### 4.5 Beginner vs expert register

| | Beginner (TF1, M6 for an international) | Expert (Canal+, beIN) |
| --- | --- | --- |
| Vocabulary | centre, frappe, égalisation, remplaçant, gardien | demi-espace, bloc bas, transition, pressing, entre les lignes, faux neuf, couverture |
| Explaining | the stakes ("le match est relancé"), never the rules | the mechanism ("le bloc a reculé de dix mètres") |
| Names | first name plus surname at first mention, club named | surname, often with the article for a star ("le Fontaine des grands soirs" style is rare, avoid) |

### 4.6 Calques to avoid (French)

| Sounds translated | Real French |
| --- | --- |
| il trouve le filet / il l'enterre | il marque, il trompe le gardien, au fond des filets |
| ses chances de gagner grimpent à 36 % | not said; "Wexmoor peut y croire" at most |
| momentum | temps fort, dynamique, Wexmoor pousse |
| tout reprendre à zéro | tout est à refaire |
| prendre des points après avoir été mené | revenir au score, aller chercher des points après avoir été mené |
| clean sheet | ne pas encaisser de but, garder sa cage inviolée |
| poteau arrière / poteau avant | second poteau / premier poteau |
| il délivre (for every pass) | il sert, il trouve, il décale |
| un match de deux mi-temps | deux mi-temps très différentes |
| "Vers Rasmussen." | "Pour Rasmussen." or just "Rasmussen." |

## 5. What never appears in either language

- Win probability or "chance of a win" in any form, and any percentage after a goal. Possession share is read at half-time from a graphic,
  at most, never in the goal reaction.
- xG in speech. DAZN and Sky show it on graphics; a pundit may mention it once in a studio segment. A live caller does not.
- Speeds, distances in metres beyond the shot distance ("aus zwanzig Metern", "des vingt mètres" are real and fine), pass counts.
- "The model", "the data", "statistically". The expert knows things, he does not compute them.
- Two numbers in one sentence after a goal, except score plus minute.
- Neutral passive ticker forms for play ("Abgefangen von...", "Intercepté par..."). They belong to a live text ticker, not to a voice.

Numbers that are fine: the score in words, the minute, "sein drittes Tor", "sa troisième réalisation", the time left, "dreimal in dieser
Saison einen Rückstand aufgeholt".

## 6. Current insert lines checked

| Current line | Verdict | Closer to real |
| --- | --- | --- |
| Abgefangen von Ibsen. | ticker passive | Ibsen geht dazwischen. |
| Brustannahme. | caption noun | Rasmussen, mit der Brust. |
| Lang geschlagen auf Tavares. | half construction | Lang auf Tavares. |
| TOR! Fontaine macht ihn rein, 1-1! | good call, wrong score format | Tooor! Fontaine! Eins zu eins! |
| TOR für Wexmoor Athletic! Fontaine netzt ein, es steht 1-1! | print verb, score format | Und da ist der Ausgleich! Fontaine! Eins zu eins! |
| Der Ausgleich verändert alles, Wexmoor glaubt jetzt wieder an den Sieg. | generic, no picture | Der Ballverlust von Tamsworth, und dann geht's ganz schnell. Viel zu einfach. |
| Wexmoor glaubt wieder an den Sieg, die Siegchance steigt auf 36 Prozent. | data readout, no expert says it | Jetzt kippt das Ding. Tamsworth hat sich zu weit zurückgezogen, das rächt sich. |
| Intercepté par Ibsen. | ticker passive | Ibsen intercepte ! |
| Vers Rasmussen. | wrong preposition | Pour Rasmussen. |
| Long ballon vers Tavares. | preposition | Le jeu long pour Tavares. |
| BUT ! Fontaine ne tremble pas, 1-1 ! | good | BUT ! Fontaine ! Un partout ! |
| BUT pour Wexmoor Athletic ! Fontaine fait mouche, c'est 1-1 ! | fine, a bit written | BUT de Fontaine ! Wexmoor égalise ! |
| Wexmoor revient à égalité, et Tamsworth doit tout reprendre à zéro. | flat idiom | Wexmoor revient, et tout est à refaire pour Tamsworth. |
| Wexmoor reprend confiance, ses chances de gagner grimpent à 36 %. | data readout | Regardez le trou entre les deux centraux. Tamsworth a voulu gérer, ça se paie. |
| Wexmoor sollte man nicht abschreiben, die Mannschaft hat schon drei Mal nach Rückstand gepunktet. | close, slightly stiff | Und Wexmoor darf man nie abschreiben, dreimal haben sie in dieser Saison schon einen Rückstand aufgeholt. |

## 7. Model lines

Spoken form (scores in words). Tags: C = caller, E = expert; B = beginner, X = expert register.

### German

1. C, both: "Ibsen geht dazwischen... Rasmussen... mit der Brust... lang auf Tavares!"
2. C, both: "Tavares legt ab, Fontaine... zieht ab... Tooor!"
3. C, both: "Und da ist der Ausgleich! Fontaine! Fontaine! Eins zu eins!"
4. C, B: "Der eingewechselte Fontaine, keine zehn Minuten auf dem Platz, und Wexmoor ist wieder da!"
5. C, X: "Der Joker sticht! Einundsiebzigste Minute, und hier ist wieder alles offen."
6. C, B: "Das hatte sich angedeutet, Wexmoor hat jetzt schon eine ganze Weile Druck gemacht."
7. E, B: "Schau dir an, wie schnell das geht. Ballgewinn, ein langer Ball, und Tamsworth ist nicht sortiert."
8. E, X: "Der Ballverlust im Zentrum tut weh, und dann rückt die Kette nicht raus. Viel zu einfach."
9. E, X: "Wie Rasmussen den mit der Brust mitnimmt und sofort lang spielt, das ist schon stark."
10. E, X: "Tavares mit dem Auge, legt ihn perfekt in den Lauf. Da musst du als Innenverteidiger mitgehen."
11. E, both: "Ganz ehrlich, Tamsworth hat sich zu weit zurückgezogen. Das rächt sich jetzt."
12. E, B: "Jetzt kippt das Spiel. Wexmoor hat Oberwasser, und die Zuschauer merken das."
13. C, both: "Noch knapp zwanzig Minuten. Und Wexmoor will mehr."
14. C, before the build-up, both: "Und man darf Wexmoor nie abschreiben, dreimal haben sie in dieser Saison schon einen Rückstand aufgeholt."

### French

1. C, both: "Ibsen intercepte ! Rasmussen, contrôle poitrine... le jeu long pour Tavares !"
2. C, both: "Tavares remet pour Fontaine... Fontaine frappe... BUUUT !"
3. C, both: "BUT de Fontaine ! Fontaine ! Wexmoor égalise ! Un partout !"
4. C, B: "Fontaine, entré il y a dix minutes, remet Wexmoor dans le match !"
5. C, X: "Coaching gagnant ! Soixante et onzième minute, et le match est relancé."
6. C, B: "On a un match ! Tout est à refaire pour Tamsworth."
7. E, B: "Regardez, tout part d'un ballon perdu au milieu, et derrière Tamsworth n'est pas en place."
8. E, X: "Il y a un trou énorme entre les deux centraux. Personne ne suit l'appel de Fontaine."
9. E, X: "Le contrôle de Rasmussen, il faut le voir. Propre, et tout de suite le jeu long."
10. E, X: "La remise de Tavares en une touche, parfaite. Fontaine n'a plus qu'à ouvrir son pied."
11. E, both: "Franchement, Tamsworth a reculé, a voulu gérer, et ça se paie."
12. E, B: "Là, Wexmoor a un temps fort. Le stade pousse, et Tamsworth subit."
13. C, both: "Il reste vingt minutes, et Wexmoor y croit."
14. C, before the build-up, both: "Attention à Wexmoor, qui est déjà revenu au score trois fois cette saison."

Each expert line names a picture (ball loss, gap, touch, lay-off) before it names a consequence. That is the pattern the current analyst lines
miss.

## 8. What this means for our bank and prompt (for the plan owner, nothing changed)

1. **Analyst angle after a goal:** cause first (which touch, which mistake, which sub), then one idiom for the consequence. The win
   probability can stay on screen as a graphic; it should not be spoken. Today the prompt's good example ("go-ahead at 2-1 with 58 percent")
   teaches the opposite.
2. **Pronoun rule conflict:** the template tests forbid gendered pronouns. Real German and French play-by-play leans on "er", "ihn", "den",
   "il", "le" all the time ("Den macht er!", "il le met au fond"). Without them the lines sound like captions. If the squads are male, the
   rule makes de and fr less real; options are to allow pronouns per team gender in meta, or to keep the rule and accept the cost.
3. **Score format:** German captions "1:1", spoken "eins zu eins"; French "1-1", spoken "un partout". `shape_for_tts` says "un à un", which is
   understandable but not what a French caller shouts.
4. **Booth names:** a German or French channel with an English-named pair (Ewan Marsh, Nadia Rowe) reads as dubbed. Local booth names per
   language would help the illusion; that is a persona decision.
5. **Name chains need gaps, not words:** "Auf Fontaine." / "Pour Fontaine." are fine; the passive and noun-only fragments should go.
6. **Native read:** everything here is from published usage and broadcast knowledge, not from a native speaker listening to our audio. Both
   banks still need that read before the video (already in Known issues).

## Sources and caveats

- Acerenza, G. (2013), "Les émotions dans les commentaires sportifs en direct de la Coupe du monde de football", Presses Sorbonne Nouvelle,
  https://books.openedition.org/psn/2531: French live commentary of 1998 and 2006 is built from name sequences and verbless, exclamatory
  sentences, with repeated exclamations ("quelle occasion, quelle occasion") and interjections ("aïe, aïe, aïe"); the journalist describes
  and reacts, the consultant analyses.
- docs/COMMENTATOR.md in this repo (SoccerNet-Echoes counts): 56% of segments are 5 words or fewer, a goal raises the pace by about a fifth.
  The patterns above fit those counts.
- Phrase lists (German Floskeln, French TV idioms such as "coaching gagnant", "on a un match", "tout est à refaire", "der Joker sticht")
  are common broadcast usage from general knowledge; short phrases only, no transcript quoted. Broadcaster names are style references, no
  real commentator is imitated in the model lines.
