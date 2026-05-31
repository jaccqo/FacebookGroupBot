# Facebook Group Bot

A Playwright-powered Facebook automation bot for:

* Discovering Facebook groups
* Joining groups automatically
* Answering join questions using AI
* Opening group member pages
* Extracting and saving members
* Opening member profiles
* Drafting personalized messages
* Preventing duplicate outreach
* Managing AI spending with monthly limits
* Running continuously with configurable cooldowns

---

# Features

## Group Discovery

Search Facebook groups using custom keywords.

Example:

```env
SEARCH_QUERY=ישראלים ב
```

The bot will:

1. Search Facebook
2. Open group search results
3. Scroll through groups
4. Save discovered groups to SQLite

---

## Automatic Group Joining

The bot can automatically join Facebook groups.

When join questions appear:

* Known questions are answered using built-in rules
* Unknown questions are sent to AI
* Answers are submitted automatically

Examples:

```txt
Where do you live?
Why do you want to join?
Are you Israeli?
```

---

## AI-Powered Join Questions

The bot uses Anthropic Claude when it encounters questions it doesn't recognize.

The AI answers using your configured profile:

```env
FB_NAME=John Smith
FB_AGE=25
FB_LOCATION=New York, NY
```

Example:

Question:

```txt
Why would you like to join this group?
```

Answer:

```txt
I'd like to connect with the community and learn more.
```

The AI never identifies itself as AI and answers as the configured profile.

---

# AI Budget Protection

All AI usage is tracked locally.

File:

```txt
data/ai_usage.json
```

Configuration:

```env
AI_MONTHLY_CAP_USD=150
AI_MONTHLY_STOP_AT_PERCENT=90
```

Meaning:

```txt
Maximum monthly budget: $150
Bot stops AI usage at: $135
```

This prevents unexpected API bills.

---

# Member Extraction

After joining a group, the bot automatically opens:

```txt
https://facebook.com/groups/{group_id}/members
```

and extracts:

* Name
* Profile URL
* Location
* Occupation
* Admin status
* Moderator status
* Verification status

Members are stored in SQLite.

---

# Member Messaging

Messages come from:

```txt
messages.json
```

Example:

```json
{
  "messages": [
    {
      "id": 1,
      "text": "Hey {{name}}, how are you doing?",
      "delay_after": 25
    },
    {
      "id": 2,
      "text": "I saw you in the group and thought I'd reach out 👋",
      "delay_after": 30
    }
  ],
  "settings": {
    "random_order": true,
    "use_placeholders": true,
    "min_delay": 20,
    "max_delay": 45
  }
}
```

Placeholder support:

```txt
{{name}}
```

Example result:

```txt
Hey Sarah, how are you doing?
```

The bot opens Messenger and types the selected message.

---

# Duplicate Protection

The bot tracks members that have already been contacted.

Database table:

```txt
member_messages
```

This prevents:

* Duplicate messages
* Duplicate drafts
* Re-processing the same member

---

# Member Filters

Skip specific member types.

Configuration:

```env
SKIP_ADMINS=true
SKIP_MODERATORS=true
SKIP_VERIFIED=false
```

| Setting         | Description              |
| --------------- | ------------------------ |
| SKIP_ADMINS     | Ignore group admins      |
| SKIP_MODERATORS | Ignore moderators        |
| SKIP_VERIFIED   | Ignore verified profiles |

Recommended:

```env
SKIP_ADMINS=true
SKIP_MODERATORS=true
```

---

# Cooldowns

Randomized cooldowns help reduce aggressive activity.

Configuration:

```env
GROUP_COOLDOWN_MIN=8
GROUP_COOLDOWN_MAX=18

MEMBER_COOLDOWN_MIN=20
MEMBER_COOLDOWN_MAX=45

PROFILE_COOLDOWN_MIN=5
PROFILE_COOLDOWN_MAX=12

SCROLL_COOLDOWN_MIN=2
SCROLL_COOLDOWN_MAX=5
```

---

# Run Modes

## Scrape Mode

Search Facebook and process discovered groups.

```env
RUN_MODE=scrape
SEARCH_QUERY=ישראלים ב
```

---

## Single Group Mode

Useful for testing.

```env
RUN_MODE=single

SINGLE_GROUP_URL=https://web.facebook.com/groups/examplegroup/
```

The bot will:

1. Open the specified group
2. Join if necessary
3. Open the members page
4. Process members

---

# Facebook Account Configuration

The bot uses credentials from:

```py
config.py
```

Configuration:

```env
FB_EMAIL=your_email@example.com
FB_PASSWORD=your_password

HEADLESS=false
```

Settings:

| Variable    | Description             |
| ----------- | ----------------------- |
| FB_EMAIL    | Facebook login email    |
| FB_PASSWORD | Facebook login password |
| HEADLESS    | Run browser without UI  |

Example:

```env
HEADLESS=true
```

Runs Chromium in headless mode.

Example:

```env
HEADLESS=false
```

Shows the browser window.

---

# Browser Profile

The bot stores session data inside:

```txt
profiles/facebook-profile
```

This allows:

* Saved Facebook login
* Persistent cookies
* Reduced login prompts
* Faster startup

After the first login, Facebook sessions are typically reused.

---

# Environment Variables

Create:

```txt
.env
```

Example:

```env
# Facebook login

FB_EMAIL=your_email@example.com
FB_PASSWORD=your_password

# Facebook profile used by AI

FB_NAME=John Smith
FB_AGE=25
FB_LOCATION=New York, NY

# Browser

HEADLESS=false

# Run mode

RUN_MODE=single

SEARCH_QUERY=ישראלים ב

SINGLE_GROUP_URL=https://web.facebook.com/groups/examplegroup/

# Sleep between cycles

SLEEP_SECONDS=21600

# Anthropic

ANTHROPIC_API_KEY=your_api_key_here

AI_MONTHLY_CAP_USD=150
AI_MONTHLY_STOP_AT_PERCENT=90

# Member filters

SKIP_ADMINS=true
SKIP_MODERATORS=true
SKIP_VERIFIED=false

# Cooldowns

GROUP_COOLDOWN_MIN=8
GROUP_COOLDOWN_MAX=18

MEMBER_COOLDOWN_MIN=20
MEMBER_COOLDOWN_MAX=45

PROFILE_COOLDOWN_MIN=5
PROFILE_COOLDOWN_MAX=12

SCROLL_COOLDOWN_MIN=2
SCROLL_COOLDOWN_MAX=5
```

---

# Database

SQLite database:

```txt
data/bot.db
```

Tables:

```txt
groups
members
group_members
member_messages
```

### groups

Stores discovered groups.

### members

Stores member profiles.

### group_members

Links members to groups.

### member_messages

Tracks drafted and sent messages.

---

# Continuous Operation

The bot is designed to run continuously.

Configuration:

```env
SLEEP_SECONDS=21600
```

Meaning:

```txt
Sleep for 6 hours between runs.
```

If an exception occurs:

* Traceback is logged
* Browser closes safely
* Bot sleeps
* Bot resumes automatically

---

# Installation

Install dependencies:

```bash
pip install -r requirements.txt
```

Install Playwright browsers:

```bash
playwright install
```

Create environment file:

```bash
cp .env.example .env
```

Edit:

```txt
.env
```

with your own settings.

---

# Running

Start:

```bash
python main.py
```

Stop:

```txt
CTRL + C
```

---

# Project Structure

```txt
project/
│
├── app.py
├── bot.py
├── ai.py
├── auth.py
├── browser.py
├── config.py
├── db.py
│
├── messages.json
├── .env
│
├── profiles/
│   └── facebook-profile/
│
├── data/
│   ├── bot.db
│   └── ai_usage.json
│
└── README.md
```

---

# Disclaimer

Use responsibly and ensure your usage complies with Facebook's Terms of Service, local laws, and platform policies. You are responsible for how the software is used.
