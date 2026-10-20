"""Template bank for the fast path (no model).

TEMPLATES[kind][lang][style] is a list of variants ordered short to long, so the
director can pick the longest one that fits the time it has. Every number in a
template comes from a placeholder, never from the text itself.
"""
from __future__ import annotations

T: dict[str, dict[str, dict[str, list[str]]]] = {
    "kickoff_start": {
        "en": {
            "beginner": ["We're underway!", "And we're off! {home} against {away}, here we go."],
            "expert": ["We're underway.", "Kick-off: {home} at home to {away}. Let's see who settles first."],
        },
        "de": {
            "beginner": ["Es geht los!", "Und los geht's! {home} gegen {away}."],
            "expert": ["Anpfiff.", "Anstoß: {home} empfängt {away}. Mal sehen, wer zuerst ins Spiel findet."],
        },
        "fr": {
            "beginner": ["C'est parti !", "Et c'est parti ! {home} contre {away}."],
            "expert": ["Coup d'envoi.", "Coup d'envoi : {home} reçoit {away}. Voyons qui trouve ses marques en premier."],
        },
    },
    "shot_goal": {
        "en": {
            "beginner": ["GOAL! {player}!", "GOAL for {team}! {player} scores, and it's {score}."],
            "expert": ["GOAL! {player}!", "{player} scores for {team}! {score}, from a chance worth {xg} expected goals."],
        },
        "de": {
            "beginner": ["TOR! {player}!", "TOR für {team}! {player} trifft, es steht {score}."],
            "expert": ["TOR! {player}!", "{player} trifft für {team}! {score}, aus einer Chance mit {xg} erwarteten Toren."],
        },
        "fr": {
            "beginner": ["BUT ! {player} !", "BUT pour {team} ! {player} marque, et c'est {score}."],
            "expert": ["BUT ! {player} !", "{player} marque pour {team} ! {score}, sur une occasion à {xg} buts attendus."],
        },
    },
    "shot_saved": {
        "en": {
            "beginner": ["Saved by {keeper}!", "{player} shoots, but {keeper} saves it!"],
            "expert": ["{keeper} saves!", "{player} shoots, {keeper} keeps it out. That was worth {xg} expected goals."],
        },
        "de": {
            "beginner": ["Gehalten von {keeper}!", "{player} schießt, aber {keeper} hält!"],
            "expert": ["{keeper} hält!", "{player} schießt, {keeper} wehrt ab. Die Chance hatte {xg} erwartete Tore."],
        },
        "fr": {
            "beginner": ["Arrêt de {keeper} !", "{player} tire, mais {keeper} détourne !"],
            "expert": ["{keeper} repousse !", "{player} frappe, {keeper} sort le ballon. L'occasion valait {xg} buts attendus."],
        },
    },
    "shot_off": {
        "en": {
            "beginner": ["{player} shoots, and misses.", "{player} tries a shot, but it goes wide of the goal."],
            "expert": ["{player} shoots wide.", "{player} pulls the trigger, but it's off target. That was worth {xg} expected goals."],
        },
        "de": {
            "beginner": ["{player} schießt, daneben.", "{player} versucht es, aber der Ball geht am Tor vorbei."],
            "expert": ["{player} schießt vorbei.", "{player} zieht ab, aber neben das Tor. Die Chance hatte {xg} erwartete Tore."],
        },
        "fr": {
            "beginner": ["{player} tire, à côté.", "{player} tente sa chance, mais le ballon passe à côté du but."],
            "expert": ["{player} tire à côté.", "{player} frappe, mais c'est cadré à côté. L'occasion valait {xg} buts attendus."],
        },
    },
    "shot_blocked": {
        "en": {
            "beginner": ["Blocked!", "{player} shoots, but a defender gets in the way."],
            "expert": ["Blocked.", "{player} lets fly, but a defender gets a body in the way."],
        },
        "de": {
            "beginner": ["Geblockt!", "{player} schießt, aber ein Verteidiger wirft sich dazwischen."],
            "expert": ["Geblockt.", "{player} zieht ab, aber die Abwehr blockt den Schuss."],
        },
        "fr": {
            "beginner": ["Contré !", "{player} tire, mais un défenseur se met en travers."],
            "expert": ["Contré.", "{player} frappe, mais la défense contre le tir."],
        },
    },
    "shot_post": {
        "en": {
            "beginner": ["Off the post!", "{player} hits the post! So close."],
            "expert": ["Off the post!", "{player} hits the woodwork! {xg} expected goals, and nothing to show for it."],
        },
        "de": {
            "beginner": ["Pfosten!", "{player} trifft den Pfosten! So knapp."],
            "expert": ["Pfosten!", "{player} trifft das Aluminium! {xg} erwartete Tore, und doch kein Treffer."],
        },
        "fr": {
            "beginner": ["Sur le poteau !", "{player} touche le poteau ! Si près."],
            "expert": ["Sur le poteau !", "{player} trouve le montant ! {xg} buts attendus, et pourtant rien."],
        },
    },
    "corner": {
        "en": {
            "beginner": ["Corner for {team}.", "A corner for {team}: the ball is played in from the corner flag."],
            "expert": ["Corner, {team}.", "Corner for {team}, a chance to put the box under pressure."],
        },
        "de": {
            "beginner": ["Ecke für {team}.", "Eckball für {team}: Der Ball wird von der Eckfahne hereingebracht."],
            "expert": ["Ecke, {team}.", "Eckball für {team}, die Chance, den Strafraum unter Druck zu setzen."],
        },
        "fr": {
            "beginner": ["Corner pour {team}.", "Corner pour {team} : le ballon est joué depuis le piquet de corner."],
            "expert": ["Corner, {team}.", "Corner pour {team}, l'occasion de mettre la surface sous pression."],
        },
    },
    "foul": {
        "en": {
            "beginner": ["Foul. Free kick for {team}.", "The referee blows the whistle for a foul, so {team} get a free kick."],
            "expert": ["Foul, free kick {team}.", "Whistle for a foul. {team} restart with a free kick."],
        },
        "de": {
            "beginner": ["Foul. Freistoß für {team}.", "Der Schiedsrichter pfeift ein Foul, also bekommt {team} einen Freistoß."],
            "expert": ["Foul, Freistoß {team}.", "Pfiff wegen eines Fouls. {team} setzt mit einem Freistoß fort."],
        },
        "fr": {
            "beginner": ["Faute. Coup franc pour {team}.", "L'arbitre siffle une faute, donc {team} obtient un coup franc."],
            "expert": ["Faute, coup franc {team}.", "Coup de sifflet pour une faute. {team} reprend sur coup franc."],
        },
    },
    "yellow": {
        "en": {
            "beginner": ["Yellow card for {player}.", "{player} gets a yellow card, a warning. A second one means a red card."],
            "expert": ["Yellow card, {player}.", "{player} goes into the book. {team} must be careful from here."],
        },
        "de": {
            "beginner": ["Gelbe Karte für {player}.", "{player} sieht Gelb, eine Verwarnung. Eine zweite bedeutet Rot."],
            "expert": ["Gelb für {player}.", "{player} kommt ins Notizbuch. {team} muss jetzt aufpassen."],
        },
        "fr": {
            "beginner": ["Carton jaune pour {player}.", "{player} prend un carton jaune, un avertissement. Un deuxième, c'est le rouge."],
            "expert": ["Jaune pour {player}.", "{player} est averti. {team} doit faire attention maintenant."],
        },
    },
    "red": {
        "en": {
            "beginner": ["RED CARD! {player} is sent off!", "Red card for {player}! {team} are down to {men} players."],
            "expert": ["RED CARD! {player} is gone!", "{player} sees red. {team} are reduced to {men} men for the rest of the match."],
        },
        "de": {
            "beginner": ["ROTE KARTE! {player} fliegt vom Platz!", "Rot für {player}! {team} spielt jetzt nur noch {men_de}."],
            "expert": ["ROT! {player} muss runter!", "{player} sieht Rot. {team} spielt den Rest der Partie nur noch {men_de}."],
        },
        "fr": {
            "beginner": ["CARTON ROUGE ! {player} est expulsé !", "Rouge pour {player} ! {team} joue maintenant {men_fr}."],
            "expert": ["ROUGE ! {player} est exclu !", "{player} prend le rouge. {team} est réduit {men_fr} pour le reste du match."],
        },
    },
    "sprint": {
        "en": {
            "beginner": ["{player} is flying down the pitch!", "{player} bursts forward at {speed} km/h!"],
            "expert": ["{player} hits {speed} km/h.", "{player} accelerates to {speed} km/h on the carry."],
        },
        "de": {
            "beginner": ["{player} rennt los!", "{player} stürmt mit {speed} km/h nach vorn!"],
            "expert": ["{player} mit {speed} km/h.", "{player} beschleunigt am Ball auf {speed} km/h."],
        },
        "fr": {
            "beginner": ["{player} file sur le terrain !", "{player} s'élance à {speed} km/h !"],
            "expert": ["{player} à {speed} km/h.", "{player} accélère à {speed} km/h balle au pied."],
        },
    },
    "half_time": {
        "en": {
            "beginner": ["Half time. {home} {hg}, {away} {ag}.", "That's half time: {home} {hg}, {away} {ag}."],
            "expert": ["Half time. {home} {hg}, {away} {ag}.", "The whistle goes for half time, {home} {hg}, {away} {ag}."],
        },
        "de": {
            "beginner": ["Halbzeit. {home} {hg}, {away} {ag}.", "Das war die erste Hälfte: {home} {hg}, {away} {ag}."],
            "expert": ["Halbzeit. {home} {hg}, {away} {ag}.", "Der Pfiff zur Pause, {home} {hg}, {away} {ag}."],
        },
        "fr": {
            "beginner": ["Mi-temps. {home} {hg}, {away} {ag}.", "C'est la mi-temps : {home} {hg}, {away} {ag}."],
            "expert": ["Mi-temps. {home} {hg}, {away} {ag}.", "Le coup de sifflet de la pause, {home} {hg}, {away} {ag}."],
        },
    },
    "full_time": {
        "en": {
            "beginner": ["Full time! {home} {hg}, {away} {ag}.", "The final whistle! It ends {home} {hg}, {away} {ag}."],
            "expert": ["Full time. {home} {hg}, {away} {ag}.", "That's it. {home} {hg}, {away} {ag} at the final whistle."],
        },
        "de": {
            "beginner": ["Abpfiff! {home} {hg}, {away} {ag}.", "Das Spiel ist aus! Es endet {home} {hg}, {away} {ag}."],
            "expert": ["Abpfiff. {home} {hg}, {away} {ag}.", "Das war's. {home} {hg}, {away} {ag} zum Schlusspfiff."],
        },
        "fr": {
            "beginner": ["Fin du match ! {home} {hg}, {away} {ag}.", "Le coup de sifflet final ! Score : {home} {hg}, {away} {ag}."],
            "expert": ["Fin du match. {home} {hg}, {away} {ag}.", "C'est terminé. {home} {hg}, {away} {ag} au coup de sifflet final."],
        },
    },
    # analyst moments, used as fallback when the model is unavailable or its line is rejected
    "goal_analysis": {
        "en": {
            "beginner": ["That goal changes the game for {team}.",
                         "That goal changes the game: {team} now have a {win_after}% chance to win."],
            "expert": ["{team}'s win probability moves from {win_before}% to {win_after}%.",
                       "Look at the swing: {team}'s win probability goes from {win_before}% to {win_after}% with that goal."],
        },
        "de": {
            "beginner": ["Dieses Tor verändert das Spiel für {team}.",
                         "Dieses Tor verändert das Spiel: {team} hat jetzt eine Siegchance von {win_after}%."],
            "expert": ["Die Siegwahrscheinlichkeit von {team} steigt von {win_before}% auf {win_after}%.",
                       "Der Ausschlag: Die Siegwahrscheinlichkeit von {team} springt mit dem Tor von {win_before}% auf {win_after}%."],
        },
        "fr": {
            "beginner": ["Ce but change la donne pour {team}.",
                         "Ce but change la donne : {team} a maintenant {win_after}% de chances de gagner."],
            "expert": ["La probabilité de victoire de {team} passe de {win_before}% à {win_after}%.",
                       "Regardez le basculement : la probabilité de victoire de {team} passe de {win_before}% à {win_after}% avec ce but."],
        },
    },
    "momentum": {
        "en": {
            "beginner": ["{team} are on top right now.",
                         "{team} are really pushing now, with {shots_n} in the last five minutes."],
            "expert": ["{team} are dominating: {share}% of the threat.",
                       "{team} have taken control, {share}% of the threat and {shots_n} in the last five minutes."],
        },
        "de": {
            "beginner": ["{team} ist gerade klar im Vorteil.",
                         "{team} drückt jetzt richtig, mit {shots_n_dat} in den letzten fünf Minuten."],
            "expert": ["{team} dominiert: {share}% der Gefahr.",
                       "{team} hat die Kontrolle übernommen, {share}% der Gefahr und {shots_n} in den letzten fünf Minuten."],
        },
        "fr": {
            "beginner": ["{team} domine en ce moment.",
                         "{team} met vraiment la pression, avec {shots_n} en cinq minutes."],
            "expert": ["{team} domine : {share}% du danger.",
                       "{team} a pris le contrôle, {share}% du danger et {shots_n} sur les cinq dernières minutes."],
        },
    },
    "big_save_analysis": {
        "en": {
            "beginner": ["What a save by {keeper}!", "{keeper} makes a huge save, that was a very good chance."],
            "expert": ["{keeper} denies a {xg} expected-goals chance.",
                       "That is a big save from {keeper}, the chance was worth {xg} expected goals."],
        },
        "de": {
            "beginner": ["Was für eine Parade von {keeper}!", "{keeper} hält überragend, das war eine richtig gute Chance."],
            "expert": ["{keeper} entschärft eine Chance mit {xg} erwarteten Toren.",
                       "Eine starke Parade von {keeper}, die Chance hatte {xg} erwartete Tore."],
        },
        "fr": {
            "beginner": ["Quel arrêt de {keeper} !", "{keeper} réalise un arrêt énorme, c'était une très belle occasion."],
            "expert": ["{keeper} détourne une occasion à {xg} buts attendus.",
                       "Un arrêt important de {keeper}, l'occasion valait {xg} buts attendus."],
        },
    },
    "big_chance_analysis": {
        "en": {
            "beginner": ["{player} should have scored there.", "A big chance missed by {player}, that one will hurt."],
            "expert": ["{player} misses a {xg} expected-goals chance.",
                       "That is a big miss from {player}, the chance was worth {xg} expected goals."],
        },
        "de": {
            "beginner": ["Da muss {player} treffen.", "Eine große Chance vergeben von {player}, das tut weh."],
            "expert": ["{player} vergibt eine Chance mit {xg} erwarteten Toren.",
                       "Das ist eine dicke Chance, die {player} liegen lässt, sie hatte {xg} erwartete Tore."],
        },
        "fr": {
            "beginner": ["{player} aurait dû marquer.", "Une grosse occasion manquée par {player}, ça va faire mal."],
            "expert": ["{player} rate une occasion à {xg} buts attendus.",
                       "Une grosse occasion manquée par {player}, elle valait {xg} buts attendus."],
        },
    },
    "shot_milestone": {
        "en": {
            "beginner": ["{player} keeps shooting.", "That's already shot number {shots} for {player}."],
            "expert": ["{shots} shots for {player}.", "{player} has now had {shots} shots."],
        },
        "de": {
            "beginner": ["{player} schießt immer wieder.", "Das ist schon der {shots}. Schuss von {player}."],
            "expert": ["{shots} Schüsse für {player}.", "{player} steht jetzt bei {shots} Schüssen."],
        },
        "fr": {
            "beginner": ["{player} tente encore sa chance.", "C'est déjà le {shots}e tir de {player}."],
            "expert": ["{shots} tirs pour {player}.", "{player} en est à {shots} tirs."],
        },
    },
}

T.update({
    "pass_final_third": {
        "en": {
            "beginner": ["{player} passes forward.", "{player} plays the ball forward to {receiver}, close to the goal."],
            "expert": ["{player} to {receiver}, into the final third.",
                       "{player} finds {receiver} in the final third, a progressive pass."],
        },
        "de": {
            "beginner": ["{player} spielt nach vorn.", "{player} spielt den Ball nach vorn zu {receiver}, nahe am Tor."],
            "expert": ["{player} auf {receiver}, ins letzte Drittel.",
                       "{player} findet {receiver} im letzten Drittel, ein progressiver Pass."],
        },
        "fr": {
            "beginner": ["{player} passe vers l'avant.", "{player} envoie le ballon vers {receiver}, près du but."],
            "expert": ["{player} pour {receiver}, dans le dernier tiers.",
                       "{player} trouve {receiver} dans le dernier tiers, une passe progressive."],
        },
    },
    "tackle_won": {
        "en": {
            "beginner": ["{player} wins the ball.", "Great tackle by {player}, and the ball is won."],
            "expert": ["{player} wins it.", "{player} makes the tackle and wins possession for {team}."],
        },
        "de": {
            "beginner": ["{player} erobert den Ball.", "Starker Zweikampf von {player}, der Ball ist gewonnen."],
            "expert": ["{player} gewinnt ihn.", "{player} gewinnt den Zweikampf und holt den Ball für {team}."],
        },
        "fr": {
            "beginner": ["{player} récupère le ballon.", "Beau tacle de {player}, le ballon est récupéré."],
            "expert": ["{player} le gagne.", "{player} remporte le duel et récupère la possession pour {team}."],
        },
    },
    "long_ball": {
        "en": {
            "beginner": ["{player} sends a long ball forward.", "{player} kicks a long pass up the pitch."],
            "expert": ["{player} goes long, {length} metres.", "{player} plays a long ball of {length} metres towards {receiver}."],
        },
        "de": {
            "beginner": ["{player} schlägt einen langen Ball.", "{player} spielt einen langen Pass weit nach vorn."],
            "expert": ["{player} schlägt ihn lang, {length} Meter.", "{player} spielt einen langen Ball über {length} Meter auf {receiver}."],
        },
        "fr": {
            "beginner": ["{player} envoie un long ballon.", "{player} tente une longue passe vers l'avant."],
            "expert": ["{player} joue long, {length} mètres.", "{player} adresse un long ballon de {length} mètres vers {receiver}."],
        },
    },
})


def variants(kind: str, lang: str, style: str) -> list[str]:
    return list(T[kind][lang][style])
