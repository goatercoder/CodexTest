import os
from datetime import datetime, timedelta
from functools import wraps

import requests
from flask import Flask, flash, jsonify, redirect, render_template, request, url_for
from flask_login import LoginManager, UserMixin, current_user, login_required, login_user, logout_user
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import UniqueConstraint, func
from werkzeug.security import check_password_hash, generate_password_hash


BASE_DIR = os.path.abspath(os.path.dirname(__file__))

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret")
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv(
    "DATABASE_URL", f"sqlite:///{os.path.join(BASE_DIR, 'music_social.db')}"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# Spotify configuration (provider-flexible via MusicProvider abstraction)
app.config["SPOTIFY_CLIENT_ID"] = os.getenv("SPOTIFY_CLIENT_ID", "")
app.config["SPOTIFY_CLIENT_SECRET"] = os.getenv("SPOTIFY_CLIENT_SECRET", "")
app.config["SPOTIFY_REDIRECT_URI"] = os.getenv(
    "SPOTIFY_REDIRECT_URI", "http://localhost:5000/auth/spotify/callback"
)


db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(180), unique=True, nullable=False)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    bio = db.Column(db.Text, default="")
    avatar_url = db.Column(db.String(255), default="https://placehold.co/120x120")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    playlists = db.relationship("Playlist", backref="creator", lazy=True)

    def set_password(self, password: str):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)


class Follow(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    follower_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    followed_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("follower_id", "followed_id", name="uq_follow"),)


class MusicConnection(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    provider = db.Column(db.String(30), nullable=False, default="spotify")
    external_user_id = db.Column(db.String(100), nullable=True)
    access_token = db.Column(db.Text, nullable=False)
    refresh_token = db.Column(db.Text, nullable=True)
    token_expires_at = db.Column(db.DateTime, nullable=True)
    connected_at = db.Column(db.DateTime, default=datetime.utcnow)


class Playlist(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    provider = db.Column(db.String(30), default="spotify")
    provider_playlist_id = db.Column(db.String(100), nullable=True)
    title = db.Column(db.String(180), nullable=False)
    description = db.Column(db.Text, default="")
    cover_url = db.Column(db.String(255), default="https://placehold.co/500x500?text=Playlist")
    is_published = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Track(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    playlist_id = db.Column(db.Integer, db.ForeignKey("playlist.id"), nullable=False)
    name = db.Column(db.String(180), nullable=False)
    artist = db.Column(db.String(180), nullable=False)
    album = db.Column(db.String(180), nullable=True)
    external_track_id = db.Column(db.String(120), nullable=True)


class Tag(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(60), unique=True, nullable=False)


class PlaylistTag(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    playlist_id = db.Column(db.Integer, db.ForeignKey("playlist.id"), nullable=False)
    tag_id = db.Column(db.Integer, db.ForeignKey("tag.id"), nullable=False)
    __table_args__ = (UniqueConstraint("playlist_id", "tag_id", name="uq_playlist_tag"),)


class PlaylistLike(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    playlist_id = db.Column(db.Integer, db.ForeignKey("playlist.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("user_id", "playlist_id", name="uq_playlist_like"),)


class PlaylistCopy(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    playlist_id = db.Column(db.Integer, db.ForeignKey("playlist.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    playlist_id = db.Column(db.Integer, db.ForeignKey("playlist.id"), nullable=False)
    body = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    kind = db.Column(db.String(50), nullable=False)
    payload = db.Column(db.Text, nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class DMThread(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_a_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    user_b_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class DMMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    thread_id = db.Column(db.Integer, db.ForeignKey("dm_thread.id"), nullable=False)
    sender_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    body = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


class SpotifyProvider:
    auth_base = "https://accounts.spotify.com/authorize"
    token_url = "https://accounts.spotify.com/api/token"
    api_base = "https://api.spotify.com/v1"

    @classmethod
    def get_auth_url(cls):
        scope = "playlist-read-private playlist-read-collaborative playlist-modify-public playlist-modify-private user-read-email"
        return (
            f"{cls.auth_base}?client_id={app.config['SPOTIFY_CLIENT_ID']}"
            f"&response_type=code&redirect_uri={app.config['SPOTIFY_REDIRECT_URI']}"
            f"&scope={scope}"
        )

    @classmethod
    def exchange_code(cls, code: str):
        response = requests.post(
            cls.token_url,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": app.config["SPOTIFY_REDIRECT_URI"],
                "client_id": app.config["SPOTIFY_CLIENT_ID"],
                "client_secret": app.config["SPOTIFY_CLIENT_SECRET"],
            },
            timeout=15,
        )
        response.raise_for_status()
        return response.json()

    @classmethod
    def profile(cls, token):
        r = requests.get(f"{cls.api_base}/me", headers={"Authorization": f"Bearer {token}"}, timeout=15)
        r.raise_for_status()
        return r.json()

    @classmethod
    def playlists(cls, token):
        r = requests.get(f"{cls.api_base}/me/playlists", headers={"Authorization": f"Bearer {token}"}, timeout=15)
        r.raise_for_status()
        return r.json().get("items", [])

    @classmethod
    def playlist_tracks(cls, token, playlist_id):
        r = requests.get(f"{cls.api_base}/playlists/{playlist_id}/tracks", headers={"Authorization": f"Bearer {token}"}, timeout=15)
        r.raise_for_status()
        return r.json().get("items", [])


PROVIDERS = {"spotify": SpotifyProvider}


def notify(user_id: int, kind: str, payload: str):
    db.session.add(Notification(user_id=user_id, kind=kind, payload=payload))


def social_stats(user_id: int):
    followers = db.session.scalar(db.select(func.count(Follow.id)).where(Follow.followed_id == user_id)) or 0
    following = db.session.scalar(db.select(func.count(Follow.id)).where(Follow.follower_id == user_id)) or 0
    total_copies = (
        db.session.query(func.count(PlaylistCopy.id))
        .join(Playlist, Playlist.id == PlaylistCopy.playlist_id)
        .filter(Playlist.user_id == user_id)
        .scalar()
        or 0
    )
    weekly_followers = (
        db.session.query(func.count(Follow.id))
        .filter(Follow.followed_id == user_id, Follow.created_at >= datetime.utcnow() - timedelta(days=7))
        .scalar()
        or 0
    )
    return {
        "followers": followers,
        "following": following,
        "total_copies": total_copies,
        "weekly_growth": weekly_followers,
    }


@app.route("/")
def home():
    trending = (
        db.session.query(Playlist, func.count(PlaylistCopy.id).label("copies"))
        .outerjoin(PlaylistCopy, Playlist.id == PlaylistCopy.playlist_id)
        .filter(Playlist.is_published.is_(True), PlaylistCopy.created_at >= datetime.utcnow() - timedelta(days=7))
        .group_by(Playlist.id)
        .order_by(func.count(PlaylistCopy.id).desc())
        .limit(8)
        .all()
    )
    recent = Playlist.query.filter_by(is_published=True).order_by(Playlist.created_at.desc()).limit(8).all()
    top_creators = (
        db.session.query(User, func.count(Follow.id).label("followers"))
        .outerjoin(Follow, Follow.followed_id == User.id)
        .group_by(User.id)
        .order_by(func.count(Follow.id).desc())
        .limit(8)
        .all()
    )
    growing = (
        db.session.query(Playlist, func.count(PlaylistCopy.id).label("copies"))
        .join(PlaylistCopy, PlaylistCopy.playlist_id == Playlist.id)
        .filter(PlaylistCopy.created_at >= datetime.utcnow() - timedelta(days=7))
        .group_by(Playlist.id)
        .order_by(func.count(PlaylistCopy.id).desc())
        .limit(8)
        .all()
    )
    return render_template("home.html", trending=trending, recent=recent, top_creators=top_creators, growing=growing)


@app.route("/feed")
@login_required
def feed():
    followed_ids = [f.followed_id for f in Follow.query.filter_by(follower_id=current_user.id).all()]
    q = Playlist.query.filter(Playlist.is_published.is_(True), Playlist.user_id.in_(followed_ids))
    items = q.order_by(Playlist.updated_at.desc()).limit(30).all()
    return render_template("feed.html", items=items)


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        username = request.form["username"].strip()
        password = request.form["password"]
        if User.query.filter((User.email == email) | (User.username == username)).first():
            flash("Email or username already exists")
            return redirect(url_for("signup"))
        user = User(email=email, username=username)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        login_user(user)
        return redirect(url_for("connect_music"))
    return render_template("auth.html", mode="signup")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        password = request.form["password"]
        user = User.query.filter_by(email=email).first()
        if not user or not user.check_password(password):
            flash("Invalid credentials")
            return redirect(url_for("login"))
        login_user(user)
        return redirect(url_for("feed"))
    return render_template("auth.html", mode="login")


@app.route("/auth/social/demo")
def social_login_demo():
    user = User.query.filter_by(email="social-demo@example.com").first()
    if not user:
        user = User(email="social-demo@example.com", username="social_demo")
        user.set_password("demo")
        db.session.add(user)
        db.session.commit()
    login_user(user)
    flash("Logged in with demo social login")
    return redirect(url_for("feed"))


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("home"))


@app.route("/connect")
@login_required
def connect_music():
    return render_template("connect.html", spotify_connected=MusicConnection.query.filter_by(user_id=current_user.id, provider="spotify").first() is not None)


@app.route("/auth/spotify")
@login_required
def spotify_auth():
    if not app.config["SPOTIFY_CLIENT_ID"] or not app.config["SPOTIFY_CLIENT_SECRET"]:
        flash("Set SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET to enable real Spotify OAuth")
        return redirect(url_for("connect_music"))
    return redirect(SpotifyProvider.get_auth_url())


@app.route("/auth/spotify/callback")
@login_required
def spotify_callback():
    code = request.args.get("code")
    if not code:
        flash("Spotify authorization failed")
        return redirect(url_for("connect_music"))
    token_data = SpotifyProvider.exchange_code(code)
    profile = SpotifyProvider.profile(token_data["access_token"])
    conn = MusicConnection.query.filter_by(user_id=current_user.id, provider="spotify").first()
    if not conn:
        conn = MusicConnection(user_id=current_user.id, provider="spotify", access_token=token_data["access_token"])
        db.session.add(conn)
    conn.access_token = token_data["access_token"]
    conn.refresh_token = token_data.get("refresh_token")
    conn.external_user_id = profile.get("id")
    conn.token_expires_at = datetime.utcnow() + timedelta(seconds=token_data.get("expires_in", 3600))
    db.session.commit()
    flash("Spotify connected")
    return redirect(url_for("import_playlists"))


@app.route("/import")
@login_required
def import_playlists():
    conn = MusicConnection.query.filter_by(user_id=current_user.id, provider="spotify").first()
    if not conn:
        flash("Connect Spotify first")
        return redirect(url_for("connect_music"))
    items = SpotifyProvider.playlists(conn.access_token)
    return render_template("import.html", playlists=items)


@app.route("/import/<provider_playlist_id>", methods=["POST"])
@login_required
def import_one(provider_playlist_id):
    conn = MusicConnection.query.filter_by(user_id=current_user.id, provider="spotify").first()
    if not conn:
        return redirect(url_for("connect_music"))

    playlists = SpotifyProvider.playlists(conn.access_token)
    data = next((p for p in playlists if p.get("id") == provider_playlist_id), None)
    if not data:
        flash("Playlist not found")
        return redirect(url_for("import_playlists"))

    playlist = Playlist(
        user_id=current_user.id,
        provider="spotify",
        provider_playlist_id=data["id"],
        title=data.get("name", "Imported Playlist"),
        description=data.get("description", ""),
        cover_url=(data.get("images") or [{"url": "https://placehold.co/500x500"}])[0]["url"],
        is_published=False,
    )
    db.session.add(playlist)
    db.session.flush()

    track_items = SpotifyProvider.playlist_tracks(conn.access_token, provider_playlist_id)
    for row in track_items:
        tr = row.get("track") or {}
        artists = ", ".join(a.get("name", "") for a in tr.get("artists", []))
        db.session.add(
            Track(
                playlist_id=playlist.id,
                name=tr.get("name", "Unknown"),
                artist=artists or "Unknown",
                album=(tr.get("album") or {}).get("name"),
                external_track_id=tr.get("id"),
            )
        )
    db.session.commit()
    flash("Playlist imported. Add tags and publish.")
    return redirect(url_for("edit_playlist", playlist_id=playlist.id))


@app.route("/playlist/new", methods=["GET", "POST"])
@login_required
def new_playlist():
    if request.method == "POST":
        p = Playlist(
            user_id=current_user.id,
            title=request.form["title"],
            description=request.form.get("description", ""),
            cover_url=request.form.get("cover_url") or "https://placehold.co/500x500",
            is_published=True,
        )
        db.session.add(p)
        db.session.commit()
        return redirect(url_for("edit_playlist", playlist_id=p.id))
    return render_template("new_playlist.html")


@app.route("/playlist/<int:playlist_id>/edit", methods=["GET", "POST"])
@login_required
def edit_playlist(playlist_id):
    playlist = db.session.get(Playlist, playlist_id)
    if not playlist or playlist.user_id != current_user.id:
        return redirect(url_for("home"))
    if request.method == "POST":
        playlist.title = request.form["title"]
        playlist.description = request.form.get("description", "")
        playlist.cover_url = request.form.get("cover_url", playlist.cover_url)
        playlist.is_published = request.form.get("publish") == "on"
        PlaylistTag.query.filter_by(playlist_id=playlist.id).delete()
        tags = [t.strip().lower() for t in request.form.get("tags", "").split(",") if t.strip()]
        for t_name in tags:
            tag = Tag.query.filter_by(name=t_name).first()
            if not tag:
                tag = Tag(name=t_name)
                db.session.add(tag)
                db.session.flush()
            db.session.add(PlaylistTag(playlist_id=playlist.id, tag_id=tag.id))
        db.session.commit()
        return redirect(url_for("playlist_detail", playlist_id=playlist.id))

    tag_names = [
        t.name
        for t in db.session.query(Tag).join(PlaylistTag, PlaylistTag.tag_id == Tag.id).filter(PlaylistTag.playlist_id == playlist.id)
    ]
    tracks = Track.query.filter_by(playlist_id=playlist.id).limit(50).all()
    return render_template("edit_playlist.html", playlist=playlist, tag_names=tag_names, tracks=tracks)


@app.route("/playlist/<int:playlist_id>", methods=["GET", "POST"])
def playlist_detail(playlist_id):
    playlist = db.session.get(Playlist, playlist_id)
    if not playlist or not playlist.is_published:
        return redirect(url_for("home"))

    if request.method == "POST" and current_user.is_authenticated:
        body = request.form.get("comment", "").strip()
        if body:
            db.session.add(Comment(user_id=current_user.id, playlist_id=playlist.id, body=body))
            notify(playlist.user_id, "comment", f"{current_user.username} commented on {playlist.title}")
            db.session.commit()

    creator = db.session.get(User, playlist.user_id)
    tags = db.session.query(Tag).join(PlaylistTag, PlaylistTag.tag_id == Tag.id).filter(PlaylistTag.playlist_id == playlist.id).all()
    comments = (
        db.session.query(Comment, User.username)
        .join(User, User.id == Comment.user_id)
        .filter(Comment.playlist_id == playlist.id)
        .order_by(Comment.created_at.desc())
        .all()
    )
    like_count = db.session.scalar(db.select(func.count(PlaylistLike.id)).where(PlaylistLike.playlist_id == playlist.id)) or 0
    copy_count = db.session.scalar(db.select(func.count(PlaylistCopy.id)).where(PlaylistCopy.playlist_id == playlist.id)) or 0
    return render_template(
        "playlist.html",
        playlist=playlist,
        creator=creator,
        tags=tags,
        comments=comments,
        like_count=like_count,
        copy_count=copy_count,
    )


@app.route("/playlist/<int:playlist_id>/like", methods=["POST"])
@login_required
def like_playlist(playlist_id):
    if not PlaylistLike.query.filter_by(user_id=current_user.id, playlist_id=playlist_id).first():
        db.session.add(PlaylistLike(user_id=current_user.id, playlist_id=playlist_id))
        playlist = db.session.get(Playlist, playlist_id)
        if playlist:
            notify(playlist.user_id, "like", f"{current_user.username} liked {playlist.title}")
        db.session.commit()
    return redirect(url_for("playlist_detail", playlist_id=playlist_id))


@app.route("/playlist/<int:playlist_id>/copy", methods=["POST"])
@login_required
def copy_playlist(playlist_id):
    playlist = db.session.get(Playlist, playlist_id)
    if not playlist:
        return redirect(url_for("home"))
    conn = MusicConnection.query.filter_by(user_id=current_user.id, provider="spotify").first()
    if not conn:
        flash("Connect Spotify to copy playlists to your account")
        return redirect(url_for("connect_music"))
    db.session.add(PlaylistCopy(user_id=current_user.id, playlist_id=playlist_id))
    notify(playlist.user_id, "copy", f"{current_user.username} copied {playlist.title}")
    db.session.commit()
    flash("Playlist copy registered. API push to Spotify can be plugged into provider strategy here.")
    return redirect(url_for("playlist_detail", playlist_id=playlist_id))


@app.route("/profile/<username>")
def profile(username):
    user = User.query.filter_by(username=username).first_or_404()
    playlists = Playlist.query.filter_by(user_id=user.id, is_published=True).order_by(Playlist.created_at.desc()).all()
    stats = social_stats(user.id)
    return render_template("profile.html", user=user, playlists=playlists, stats=stats)


@app.route("/follow/<int:user_id>", methods=["POST"])
@login_required
def follow(user_id):
    if user_id == current_user.id:
        return redirect(url_for("home"))
    if not Follow.query.filter_by(follower_id=current_user.id, followed_id=user_id).first():
        db.session.add(Follow(follower_id=current_user.id, followed_id=user_id))
        target = db.session.get(User, user_id)
        if target:
            notify(user_id, "follow", f"{current_user.username} followed you")
        db.session.commit()
    return redirect(request.referrer or url_for("home"))


@app.route("/discover")
def discover():
    tag = request.args.get("tag", "").strip().lower()
    query = Playlist.query.filter_by(is_published=True)
    if tag:
        query = query.join(PlaylistTag, PlaylistTag.playlist_id == Playlist.id).join(Tag, Tag.id == PlaylistTag.tag_id).filter(Tag.name == tag)
    playlists = query.order_by(Playlist.created_at.desc()).limit(40).all()
    trending_tags = (
        db.session.query(Tag.name, func.count(PlaylistTag.id).label("count"))
        .join(PlaylistTag, PlaylistTag.tag_id == Tag.id)
        .group_by(Tag.name)
        .order_by(func.count(PlaylistTag.id).desc())
        .limit(20)
        .all()
    )
    return render_template("discover.html", playlists=playlists, trending_tags=trending_tags, tag=tag)


@app.route("/search")
def search():
    q = request.args.get("q", "").strip()
    playlists, creators, tags = [], [], []
    if q:
        playlists = Playlist.query.filter(Playlist.title.ilike(f"%{q}%"), Playlist.is_published.is_(True)).limit(12).all()
        creators = User.query.filter(User.username.ilike(f"%{q}%")).limit(12).all()
        tags = Tag.query.filter(Tag.name.ilike(f"%{q}%")).limit(12).all()
    return render_template("search.html", q=q, playlists=playlists, creators=creators, tags=tags)


@app.route("/messages", methods=["GET", "POST"])
@login_required
def messages():
    if request.method == "POST":
        recipient_username = request.form["recipient"].strip()
        body = request.form["body"].strip()
        recipient = User.query.filter_by(username=recipient_username).first()
        if recipient and body:
            a, b = sorted([current_user.id, recipient.id])
            thread = DMThread.query.filter_by(user_a_id=a, user_b_id=b).first()
            if not thread:
                thread = DMThread(user_a_id=a, user_b_id=b)
                db.session.add(thread)
                db.session.flush()
            db.session.add(DMMessage(thread_id=thread.id, sender_id=current_user.id, body=body))
            notify(recipient.id, "dm", f"New message from {current_user.username}")
            db.session.commit()

    thread_rows = DMThread.query.filter((DMThread.user_a_id == current_user.id) | (DMThread.user_b_id == current_user.id)).all()
    inbox = []
    for t in thread_rows:
        partner_id = t.user_b_id if t.user_a_id == current_user.id else t.user_a_id
        partner = db.session.get(User, partner_id)
        messages = DMMessage.query.filter_by(thread_id=t.id).order_by(DMMessage.created_at.desc()).limit(10).all()
        inbox.append({"partner": partner, "messages": list(reversed(messages))})
    return render_template("messages.html", inbox=inbox)


@app.route("/notifications")
@login_required
def notifications():
    items = Notification.query.filter_by(user_id=current_user.id).order_by(Notification.created_at.desc()).limit(50).all()
    return render_template("notifications.html", items=items)


@app.route("/metrics")
def metrics():
    data = {
        "playlists_published": Playlist.query.filter_by(is_published=True).count(),
        "weekly_playlist_copies": PlaylistCopy.query.filter(PlaylistCopy.created_at >= datetime.utcnow() - timedelta(days=7)).count(),
        "weekly_comments": Comment.query.filter(Comment.created_at >= datetime.utcnow() - timedelta(days=7)).count(),
        "weekly_dms": DMMessage.query.filter(DMMessage.created_at >= datetime.utcnow() - timedelta(days=7)).count(),
        "weekly_returning_users": db.session.query(func.count(func.distinct(PlaylistCopy.user_id))).filter(PlaylistCopy.created_at >= datetime.utcnow() - timedelta(days=7)).scalar() or 0,
    }
    return jsonify(data)


@app.cli.command("init-db")
def init_db():
    db.create_all()
    print("Database initialized")


if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(host="0.0.0.0", port=5000, debug=True)
