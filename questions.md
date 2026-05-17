# GameHub — Understanding the system

10 questions to test your understanding of the data flow and architecture.
Work through them in order: read the code first, then run the app, then try to break things.

---

## How to investigate

You will need three things:

**1. Read the source code**
Start with `models.py` (the schema), then `seed.py` (the data), then `app.py` (the logic).
Many questions are answered entirely by reading carefully.

**2. Run the app and interact with it**
Use the UI at `http://localhost:5000` or send requests with curl or Postman.
Observe what actually happens — don't just reason about it.

```bash
# Example: log an activity for nova (id=1) on Hollow Knight (id=1)
curl -X POST http://localhost:5000/activities \
  -H "Content-Type: application/json" \
  -d '{"user_id": 1, "game_id": 1, "action": "started"}'
```

**3. Query the database directly**
Open `gamehub.db` with a SQLite tool and inspect the actual rows.

```bash
sqlite3 gamehub.db
.tables
SELECT COUNT(*) FROM notifications;
SELECT * FROM notifications WHERE user_id = 1;
```

Or use a GUI: **DB Browser for SQLite** (free, recommended).

---

## Suggested approach

| Phase | Questions | What you are doing |
|-------|-----------|-------------------|
| Read first | 1, 4, 8, 10 | Understand the code before touching anything |
| Then run it | 3, 6, 9    | Observe actual behaviour                     |
| Then break it | 2, 5, 7  | Try things, hit walls, reason about why      |

---

## Questions

**1.** When a user logs a new activity, how many database tables are written to?
List them and explain why each one is affected.

I think 2
- activities: because this is core data belong logged. Thats why we make the request in the first place.
- notification: we get one notification row every one friend, for every friend of the user. we have that notification logic in the activity endpoint.

---

**2.** You call `DELETE FROM users WHERE id = 3` directly in SQLite.
What happens, and why? What would you need to do instead?

it will fail. All the other tables have foreign keys pointing to users. Like activities, notifs, friends all reference users. So I cant just delete it.

this is in app.py:
# The order matters — notifications reference activities, so activities can't
# be deleted before notifications. Friends reference users twice. Good luck.

so based on that i think i start with the notifications first instead.
---

**3.** User `nova` changes her username to `nova_2`.
She then checks her friends' notification feeds.
What do they see — the old name or the new one? Why?

they will see the old one. whatever username is showing is already stored and used like this

# msg = f"{actor['username']} just {data['action']} playing # {game['title']}!"

So i think its already saved and wont be updated. They'll just see 'nova'
---

**4.** Trace the full journey of a `POST /activities` request.
Starting from the HTTP call, list every operation that happens before the response is returned.

1. flask receives the HTTP POST. routes it to create_activity()
2. user_id, game_id, action are read
3.row is inserted into the activities table
4.new activity row, user name, game's title is fetched
5, friends of the user are fetched
6. for each friend, a notification message string is built and a row is inserted into notifications
7. all inserts committed
8.activity row returned as JSON with a 201 status
---

**5.** `pixel_queen` opts out of activity tracking.
A teammate adds an `opted_out` boolean column to the `users` table and updates the `POST /activities` API route to check it.
Is the feature fully implemented? What did they miss?

No. The UI has a separate route (POST /view/activities) that also inserts activities and sends notifications. They didnt update that one.

So a user who opted out would still get their activities logged and notifications sent if on web. Need to do it for both routes
---

**6.** How many rows are created in the database when `nova` logs one activity, given the current seed data?
Show your working.

nova has 3 friends. So first she would get 1 row for logging the activities. For every friend we get a row. So we get 3 more rows for the friend notifs. So 4 rows
---

**7.** You need to delete `maya_r`.
In what order must you delete rows across the tables, and why does the order matter?

because we have the foreign keys, we have to delete it in an order. I cant delete a row that another table is referencing.

order: notifs, activities, user_games, friends, and users
---

**8.** The `notifications` table has a foreign key pointing to `activities`.
What happens if you try to delete an activity that has notifications attached to it?

it will again fail. Because again the notifs is referencing activities. I would need to delete that specific notifs row thats pointing to the activity first.
---

**9.** A bug is found in the game catalog — wrong genre for one game.
You fix it and restart the app to ship the change.
What else just went down, and for how long?

its a monolith so everything runs as a single process. If i restart the app it just all goes down. Also theres a comment in app.py about this:
# A one-line fix to a game title still requires restarting the whole app to ship.
# While it's down: users can't log in, activities stop, notifications stop.
---

**10.** A teammate says: *"let's just move the notification logic into its own function in `app.py`"*.
Does that solve the problem described in Task 4?
What is the actual architectural issue?

notif logic is still the same process. Moving it still means it still runs in the same request. Like I think it still has to sit inside def create_activity() because we cant get it away from the activity logic. So no I dont think it solves the problem