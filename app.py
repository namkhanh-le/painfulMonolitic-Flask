from flask import Flask, jsonify, request
from datetime import datetime, timezone
from models import init_db, get_db

app = Flask(__name__)


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# Run DB setup on startup
init_db()


# =============================================================================
# USERS
# =============================================================================

@app.route("/users", methods=["GET"])
def list_users():
    conn = get_db()
    users = conn.execute("SELECT * FROM users").fetchall()
    conn.close()
    return jsonify([dict(u) for u in users])


@app.route("/users/<int:user_id>", methods=["GET"])
def get_user(user_id):
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    if not user:
        return jsonify({"error": "User not found"}), 404
    return jsonify(dict(user))


@app.route("/users", methods=["POST"])
def create_user():
    data = request.json
    conn = get_db()
    conn.execute(
        "INSERT INTO users (username, email, password_hash, bio, created_at) VALUES (?,?,?,?,?)",
        (data["username"], data["email"], data.get("password", "hashed"), data.get("bio", ""), now())
    )
    conn.commit()
    user = conn.execute("SELECT * FROM users WHERE username = ?", (data["username"],)).fetchone()
    conn.close()
    return jsonify(dict(user)), 201


@app.route("/users/<int:user_id>", methods=["PUT"])
def update_user(user_id):
    data = request.json
    conn = get_db()
    # Note: username is used as identifier in activity messages and notifications.
    # Changing it here does NOT update those references — they're stored as plain text.
    conn.execute(
        "UPDATE users SET username = ?, email = ?, bio = ? WHERE id = ?",
        (data["username"], data["email"], data.get("bio", ""), user_id)
    )
    conn.commit()
    user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    return jsonify(dict(user))


@app.route("/users/<int:user_id>", methods=["DELETE"])
def delete_user(user_id):
    conn = get_db()

    # To delete a user, you must manually remove every row that references them.
    # The order matters — notifications reference activities, so activities can't
    # be deleted before notifications. Friends reference users twice. Good luck.

    # Step 1 — remove notifications where user is the receiver
    conn.execute("DELETE FROM notifications WHERE user_id = ?", (user_id,))

    # Step 2 — remove notifications where user is the one who triggered them
    conn.execute("DELETE FROM notifications WHERE triggered_by = ?", (user_id,))

    # Step 3 — remove activities
    conn.execute("DELETE FROM activities WHERE user_id = ?", (user_id,))

    # Step 4 — remove from user_games
    conn.execute("DELETE FROM user_games WHERE user_id = ?", (user_id,))

    # Step 5 — remove friendships (both directions)
    conn.execute("DELETE FROM friends WHERE user_id = ? OR friend_id = ?", (user_id, user_id))

    # Step 6 — finally, remove the user
    conn.execute("DELETE FROM users WHERE id = ?", (user_id,))

    conn.commit()
    conn.close()
    return jsonify({"message": "User deleted"}), 200


# =============================================================================
# GAMES
# =============================================================================

@app.route("/games", methods=["GET"])
def list_games():
    conn = get_db()
    games = conn.execute("SELECT * FROM games").fetchall()
    conn.close()
    return jsonify([dict(g) for g in games])


@app.route("/games/<int:game_id>", methods=["GET"])
def get_game(game_id):
    conn = get_db()
    game = conn.execute("SELECT * FROM games WHERE id = ?", (game_id,)).fetchone()
    conn.close()
    if not game:
        return jsonify({"error": "Game not found"}), 404
    return jsonify(dict(game))


@app.route("/games", methods=["POST"])
def create_game():
    data = request.json
    conn = get_db()
    conn.execute(
        "INSERT INTO games (title, genre, description, created_at) VALUES (?,?,?,?)",
        (data["title"], data["genre"], data.get("description", ""), now())
    )
    conn.commit()
    game = conn.execute("SELECT * FROM games WHERE title = ?", (data["title"],)).fetchone()
    conn.close()
    return jsonify(dict(game)), 201


@app.route("/games/<int:game_id>", methods=["PUT"])
def update_game(game_id):
    # Fixing a typo in a game title? Correcting a genre?
    # You'll need to restart the entire app to ship this change.
    # Users, auth, notifications — all go down with it.
    data = request.json
    conn = get_db()
    conn.execute(
        "UPDATE games SET title = ?, genre = ?, description = ? WHERE id = ?",
        (data["title"], data["genre"], data.get("description", ""), game_id)
    )
    conn.commit()
    game = conn.execute("SELECT * FROM games WHERE id = ?", (game_id,)).fetchone()
    conn.close()
    return jsonify(dict(game))


# =============================================================================
# ACTIVITIES
# =============================================================================

@app.route("/activities", methods=["GET"])
def list_activities():
    conn = get_db()
    rows = conn.execute("""
        SELECT a.*, u.username, g.title as game_title
        FROM activities a
        JOIN users u ON a.user_id = u.id
        JOIN games g ON a.game_id = g.id
        ORDER BY a.created_at DESC
    """).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/activities", methods=["POST"])
def create_activity():
    data = request.json
    conn = get_db()

    # Insert the activity
    conn.execute(
        "INSERT INTO activities (user_id, game_id, action, created_at) VALUES (?,?,?,?)",
        (data["user_id"], data["game_id"], data["action"], now())
    )
    conn.commit()

    activity = conn.execute(
        "SELECT * FROM activities WHERE user_id = ? ORDER BY id DESC LIMIT 1",
        (data["user_id"],)
    ).fetchone()

    actor = conn.execute("SELECT username FROM users WHERE id = ?", (data["user_id"],)).fetchone()
    game  = conn.execute("SELECT title FROM games WHERE id = ?", (data["game_id"],)).fetchone()

    # Notification logic lives here — because where else would it go?
    # This means you cannot disable notifications without touching this route.
    friends = conn.execute(
        "SELECT friend_id FROM friends WHERE user_id = ?", (data["user_id"],)
    ).fetchall()

    for f in friends:
        msg = f"{actor['username']} just {data['action']} playing {game['title']}!"
        conn.execute(
            "INSERT INTO notifications (user_id, triggered_by, message, activity_id, created_at) VALUES (?,?,?,?,?)",
            (f["friend_id"], data["user_id"], msg, activity["id"], now())
        )

    conn.commit()
    conn.close()
    return jsonify(dict(activity)), 201


# =============================================================================
# NOTIFICATIONS
# =============================================================================

@app.route("/notifications/<int:user_id>", methods=["GET"])
def get_notifications(user_id):
    conn = get_db()
    rows = conn.execute("""
        SELECT n.*, u.username as triggered_by_username
        FROM notifications n
        JOIN users u ON n.triggered_by = u.id
        WHERE n.user_id = ?
        ORDER BY n.created_at DESC
    """, (user_id,)).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/notifications/<int:notif_id>", methods=["DELETE"])
def delete_notification(notif_id):
    conn = get_db()
    conn.execute("DELETE FROM notifications WHERE id = ?", (notif_id,))
    conn.commit()
    conn.close()
    return jsonify({"message": "Notification deleted"})


# =============================================================================
# FRIENDS
# =============================================================================

@app.route("/friends/<int:user_id>", methods=["GET"])
def get_friends(user_id):
    conn = get_db()
    rows = conn.execute("""
        SELECT u.id, u.username, u.email, u.bio
        FROM friends f
        JOIN users u ON f.friend_id = u.id
        WHERE f.user_id = ?
    """, (user_id,)).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/friends", methods=["POST"])
def add_friend():
    data = request.json
    conn = get_db()
    # Friendship is bidirectional — two rows required
    conn.execute("INSERT INTO friends (user_id, friend_id) VALUES (?,?)", (data["user_id"], data["friend_id"]))
    conn.execute("INSERT INTO friends (user_id, friend_id) VALUES (?,?)", (data["friend_id"], data["user_id"]))
    conn.commit()
    conn.close()
    return jsonify({"message": "Friends added"}), 201


# =============================================================================

if __name__ == "__main__":
    app.run(debug=True, port=5000)
