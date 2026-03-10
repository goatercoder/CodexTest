# PulseList (Music Social Platform MVP)

A web-based social platform where playlists become social content, with Spotify integration and social mechanics.

## Features
- Email/password signup/login + demo social login flow
- Spotify OAuth connection and one-click playlist import
- Playlist metadata + tracks imported from Spotify
- Publish/edit playlists with multi-tag system
- Public profile pages with social stats
- Follow system + personalized feed
- Playlist pages with likes, comments, copy action
- Direct messages (1:1), notifications
- Discovery by tags, search across playlists/creators/tags
- Leaderboard sections on homepage
- Metrics endpoint: `/metrics`

## Architecture notes
- Provider strategy via `PROVIDERS` map (`spotify` today, extendable to future providers)
- Backend stores only metadata, social graph, and engagement events
- No audio hosting/playback

## Run locally
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export SPOTIFY_CLIENT_ID=...
export SPOTIFY_CLIENT_SECRET=...
python app.py
```

Then open `http://localhost:5000`.

## Spotify OAuth
Set:
- `SPOTIFY_CLIENT_ID`
- `SPOTIFY_CLIENT_SECRET`
- optional `SPOTIFY_REDIRECT_URI` (default `http://localhost:5000/auth/spotify/callback`)

In Spotify Developer Dashboard add the same redirect URI.
