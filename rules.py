import random

RULES_TEXT = """
🏏 **HAND CRICKET - RULES** 🏏

**How to Play:**
1️⃣ Batter types a number (1-6) in the **group chat**.
2️⃣ Bowler types a number (1-6) in the **bot's private DM**.
3️⃣ If both numbers **match** → Batter is **OUT**! 🔴
4️⃣ If numbers **differ** → Batter scores their number! 🟢

**Special Rules:**
🦆 Out for 0 runs = **DUCK**!
🔄 Strike rotates on **odd runs** (1, 3, 5) and at **end of over**.
🚫 Bowler can't use same number **3 times in an over**.
🚫 Bowler can't bowl same number **twice in a row**.
⏱ **80 seconds** AFK timeout:
   - Bowler AFK → **+6 runs** penalty!
   - Batter AFK → Batter is **OUT**!

**Modes:**
🎯 **Solo Mode** - Free-for-all! Each player bats 1 over.
👥 **Team Mode** - Team A vs Team B!

**Commands:**
/startcricket - Start a new match lobby
/joinsolo - Join solo mode
/join\\_team\\_a - Join Team A
/join\\_team\\_b - Join Team B
/forcestart - Force start the match
/bat - Choose to bat first (toss winner)
/field - Choose to field first (toss winner)
/score - View current score
/scoreboard - View full scoreboard
/teams - View teams
/sledge - Sledge the opponent!
/call - Remind AFK player
/endcricket - End the match
"""

COMMENTARY_OUT = [
    "💥 BOWLED HIM! What a delivery! Stumps are shattered! 🏏",
    "🔴 OUT! Clean bowled! Timber! 🪵",
    "☝️ HOWZAT! That's OUT! The umpire raises the finger! 🙋",
    "😱 Gone! Castled! The bails go flying! 💨",
    "🎯 DIRECT HIT on the stumps! That's the end of the innings for this batter!",
    "💀 OUT! Pack your bags, you're going home! 🧳",
    "🔥 KNOCKED HIM OVER! Beautiful bowling! 🎳",
    "❌ That's the wicket! The bowler celebrates! 🎉",
    "🚶 Walk back to the pavilion! You're DONE! 🏚️",
    "⚡ CLEANED UP! The stumps are in disarray! 💥",
]

COMMENTARY_OUT_HINDI = [
    "💥 BOWLED! Kya gend daali bhai! Stumps ud gaye! 🏏",
    "🔴 OUT! Seedha stumps pe! Lakkad! 🪵",
    "☝️ HOWZAT! Out hai bhai! Umpire ne ungli utha di! 🙋",
    "😱 Gaya! Castle ho gaya! 💨",
    "🎯 Stumps pe seedha! Inning khatam is batter ki!",
    "💀 OUT! Bag pack karo, ghar jaao! 🧳",
    "🔥 Ukhad diya! Kamaal ki bowling! 🎳",
    "❌ Wicket aa gayi! Bowler naach raha hai! 🎉",
    "🚶 Pavilion mein jaao! Khatam! 🏚️",
    "⚡ Saaf kar diya! Stumps bikhar gaye! 💥",
]

COMMENTARY_RUNS = {
    1: [
        "1️⃣ Single! Good running between the wickets! 🏃",
        "1️⃣ Tuk-tuk cricket! One run added! 📝",
        "1️⃣ Nudged away for a single! Smart batting! 🧠",
        "1️⃣ Pushed into the gap, easy single! 🎯",
    ],
    2: [
        "2️⃣ Two runs! Good placement! 🎯",
        "2️⃣ Driven through the covers for TWO! 💪",
        "2️⃣ Cut shot! They come back for two! 🏃‍♂️🏃",
        "2️⃣ Nicely timed! Two runs in the bag! 👜",
    ],
    3: [
        "3️⃣ THREE runs! Excellent running! 🏃‍♂️💨",
        "3️⃣ Three! Misfield by the fielder! 😅",
        "3️⃣ Pulled away! They run three! Great effort! 💪",
        "3️⃣ Edge flies to third man! Three runs! 🎯",
    ],
    4: [
        "4️⃣ FOUR! Boundary! 🔵 Races to the fence! 🏏💥",
        "4️⃣ SHOT! That's a beautiful FOUR! 😍",
        "4️⃣ FOUR RUNS! Creamed through the covers! ✨",
        "4️⃣ BOUNDARY! What a stroke! 🎨🏏",
        "4️⃣ Chhakka nahi par FOUR toh hai! 🔵",
    ],
    5: [
        "5️⃣ FIVE runs! Overthrow! What drama! 🎭",
        "5️⃣ Five! Misfield and overthrow! 😱",
        "5️⃣ FIVE RUNS! Chaos in the field! 🌀",
        "5️⃣ Overthrow! Five runs scored! Lucky! 🍀",
    ],
    6: [
        "6️⃣ SIX! MAXIMUM! 🚀 Out of the ground! 🏟️",
        "6️⃣ IT'S A SIX! Into the stands! 🎆🎇",
        "6️⃣ HUGE SIX! That ball is in orbit! 🌍🚀",
        "6️⃣ DHOOOOM! CHHAKKA! 💥🔥🏏",
        "6️⃣ SIX! Bowler ka confidence toot gaya! 😂",
        "6️⃣ MONSTER HIT! That's gone miles! 🦍💪",
    ],
}

COMMENTARY_RUNS_HINDI = {
    1: [
        "1️⃣ Ek run! Bhago bhago! 🏃",
        "1️⃣ Tuk-tuk! Ek run le liya! 📝",
        "1️⃣ Single mil gaya! 🧠",
    ],
    2: [
        "2️⃣ Do run! Accha shot! 🎯",
        "2️⃣ Cover drive! Do run! 💪",
        "2️⃣ Timing laga di! Do run! 👜",
    ],
    3: [
        "3️⃣ TEEN run! Kamaal ki running! 🏃‍♂️💨",
        "3️⃣ Teen! Fielder se galti! 😅",
        "3️⃣ Pull shot! Teen run! 💪",
    ],
    4: [
        "4️⃣ CHAUKAA! Boundary! 🔵🏏💥",
        "4️⃣ SHOT! Kya FOUR maara! 😍",
        "4️⃣ FOUR! Covers mein! ✨",
    ],
    5: [
        "5️⃣ PAANCH run! Overthrow! Drama! 🎭",
        "5️⃣ Paanch! Misfield aur overthrow! 😱",
    ],
    6: [
        "6️⃣ CHHAKKA! MAXIMUM! 🚀🏟️",
        "6️⃣ SIX! Stands mein gayi! 🎆🎇",
        "6️⃣ DHOOOOM! CHHAKKA! 💥🔥🏏",
        "6️⃣ MONSTER HIT! 🦍💪",
    ],
}

DUCK_MESSAGES = [
    "🦆 DUCK! 0 runs! Quack quack! That's embarrassing! 😂",
    "🦆 GOLDEN DUCK! Out for a big fat ZERO! 🥚",
    "🦆 Quack Quack! Duck out! Sharam karo! 😭🦆",
    "🦆 DUCK! Anda de diya! 🥚🦆 Kya batting thi ye!",
    "🦆 0 runs! Even a duck would score more! 🦆😂",
]

SLEDGE_MESSAGES = [
    "🗣️ Ae bhai, batting seekh ke aao! 😂",
    "🗣️ Village cricket se aaye ho kya? 🏘️😜",
    "🗣️ Ye bowler toh tujhe dinner pe bula raha hai! 🍽️",
    "🗣️ Stumps dhundh rahe ho? Peeche hain! 😂🏏",
    "🗣️ Batting chhodo, chai laao! ☕😂",
    "🗣️ Tera bat straight hai ya tera aim? 🤔😂",
    "🗣️ Bowler bol raha hai - easy target! 🎯😜",
    "🗣️ Ghar jaake gilli-danda khelo! 😂",
    "🗣️ Are you batting or sleeping? 😴🏏",
    "🗣️ My grandma bowls faster than you bat! 👵🏏",
    "🗣️ This isn't a museum, PLAY a shot! 🏛️😂",
    "🗣️ The stumps are more stable than your batting! 🪵",
    "🗣️ Tera bowling dekh ke batsman so gaya! 😴",
    "🗣️ Ye kya line-length hai? Spaceship bhej raha hai kya? 🚀😂",
]

TOSS_WON_MESSAGES = [
    "🪙 TOSS TIME! The coin spins in the air... 🌀",
]

MATCH_START_MESSAGES = [
    "🏟️ Welcome to the stadium! The crowd roars! 📣",
    "🏟️ The floodlights are ON! It's GAME TIME! 💡🏏",
]

INNINGS_BREAK_MESSAGES = [
    "☕ INNINGS BREAK! Time for chai and samosa! 🍵🥟",
    "🔄 Innings changeover! Teams switching roles! 🔁",
    "⏸️ End of innings! Let's take a breather! 💨",
]

MATCH_END_MESSAGES = [
    "🏆 MATCH OVER! What a game of cricket! 🎊🎉",
    "🎆 That's a wrap! Incredible match! 🏏✨",
]


def get_commentary(runs, lang="en"):
    if lang == "hi":
        return random.choice(COMMENTARY_RUNS_HINDI.get(runs, COMMENTARY_RUNS.get(runs, ["Scored!"])))
    return random.choice(COMMENTARY_RUNS.get(runs, ["Scored!"]))


def get_out_commentary(lang="en"):
    if lang == "hi":
        return random.choice(COMMENTARY_OUT_HINDI)
    return random.choice(COMMENTARY_OUT)


def get_duck_message():
    return random.choice(DUCK_MESSAGES)


def get_sledge():
    return random.choice(SLEDGE_MESSAGES)


def get_innings_break():
    return random.choice(INNINGS_BREAK_MESSAGES)


def get_match_end():
    return random.choice(MATCH_END_MESSAGES)


def get_match_start():
    return random.choice(MATCH_START_MESSAGES)
