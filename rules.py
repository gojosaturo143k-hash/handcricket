import random

COMMENTARY = {
    "eng": {
        "six": ["🔥 What a shot! {batter} smashes it for SIX!", "💥 Massive hit! {batter} sends it into the stands!"],
        "four": ["💯 Elegant drive by {batter}! Racing to the boundary!", "🏏 Perfect timing! {batter} finds the gap!"],
        "out": ["🎯 BOWLED 'EM! {batter} has to walk back!", "💣 Trapped! {batter} is out!"],
        "duck": ["🦆 DUCK! Oh no, {batter} walks back for a golden duck!"],
        "single": ["🏃 Quick running between the wickets! +1"],
        "timeout_bowler": ["⏰ BOWLER TIMEOUT! +6 runs awarded to the batting side. The bowler has been rotated."],
        "timeout_batter": ["⏰ BATTER TIMEOUT! 🎯 OUT!"]
    },
    "hin": {
        "six": ["🔥 Kya shot tha! {batter} ne zabardast SIX maara!", "💥 Lambi chhakka! {batter} ne udaa diya!"],
        "four": ["💯 Shandar drive! {batter} ki boundary!", "🏏 Badhiya timing! {batter} ne gap dhundh liya!"],
        "out": ["🎯 BOWLED! {batter} ko lautna padega!", "💣 Phas gaye! {batter} out ho gaye!"],
        "duck": ["🦆 DUCK! Arre {batter} bina score kiye out ho gaye!"],
        "single": ["🏃 Teji se daud liya! +1"],
        "timeout_bowler": ["⏰ BOWLER TIMEOUT! Batting side ko +6 runs mil gaye. Bowler badla gaya."],
        "timeout_batter": ["⏰ BATTER TIMEOUT! 🎯 OUT!"]
    }
}

SLEDGES = [
    "😂 Bowler ko lagta hai calculator kharab hai!",
    "🤣 Batter ne ball ko retirement plan de diya!",
    "😄 Is speed se toh turtle bhi aage nikal jayega!",
    "🤭 Yeh shot toh WhatsApp status pe bhi nahi aayega!",
    "😜 Bowler ke yahan toh seal band ho gayi hai!",
    "😂 Batter ne puchha 'Yeh wala kya hai?'",
    "🤣 Coach ne TV off kar diya hoga!",
    "😅 Strike rotate karte karte thak gaye honge!"
]

RULES_TEXT = """🏏 **HAND CRICKET RULES**

🔹 **Batting & Bowling:**
Batter types 1-6 in the GROUP.
Bowler types 1-6 in BOT's PRIVATE DM.

🔹 **Scoring:**
If numbers are DIFFERENT: Batter scores the runs they chose.
If numbers are SAME: Batter is OUT!

🔹 **Strike Rotation:**
Strike changes on odd runs (1, 3, 5).
Strike changes at the end of every over.

🔹 **Bowling Restrictions:**
Cannot bowl same number 3 times in an over.
Cannot bowl same number twice consecutively.

🔹 **Timeouts:**
If Batter/Bowler doesn't respond in 80 seconds, penalties apply!"""
