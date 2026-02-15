import os
from flask import Flask, render_template, jsonify, redirect, url_for, session, Response
from authlib.integrations.flask_client import OAuth
from flask import Response
import requests

app = Flask(__name__)

# ─── SECURITY / OAUTH CONFIG ─────────────────────────────────────────────────
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ['DATABASE_URL']
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret')  # override via env

# initialize Authlib
oauth = OAuth(app)
github = oauth.register(
    name='github',
    client_id=os.environ['GITHUB_CLIENT_ID'],
    client_secret=os.environ['GITHUB_CLIENT_SECRET'],
    access_token_url='https://github.com/login/oauth/access_token',
    authorize_url='https://github.com/login/oauth/authorize',
    api_base_url='https://api.github.com/',
    client_kwargs={'scope': 'user:email'},
)


@app.route('/')
def index():
    return render_template('index.html')

@app.route('/teams')
def teams():
    # Fetch the current standings/teams
    resp = requests.get('https://api-web.nhle.com/v1/standings/now')
    data = resp.json()
    standings = data.get('standings', [])

    # Group teams by divisionAbbrev (now a simple string in the response)
    divisions = {}
    for t in standings:
        div = t['divisionName']  # API now returns this as a string
        divisions.setdefault(div, []).append({
            'abbrev': t['teamAbbrev']['default'],
            'name': t['teamCommonName']['default'],
            'logo': t['teamLogo']
        })

    return jsonify(divisions)

@app.route('/roster/<team_abbrev>')
def roster(team_abbrev):
    # 1) fetch the raw roster
    r = requests.get(f'https://api-web.nhle.com/v1/roster/{team_abbrev}/current')
    roster_json = r.json()
    players = []

    # 2) for each skater, fetch landing/stats and pluck current-season + playoff
    for group in ('forwards', 'defensemen', 'goalies'):
        for p in roster_json.get(group, []):
            pid = p['id']
            summ = requests.get(f'https://api-web.nhle.com/v1/player/{pid}/landing').json()
            fs = summ.get('featuredStats', {})
            # current season regular
            rs = fs.get('regularSeason', {}).get('subSeason', {})
            # current season playoffs
            po = fs.get('playoffs', {}).get('subSeason', {})

            players.append({
                'headshot': p.get('headshot'),
                'name': f"{p['firstName']['default']} {p['lastName']['default']}",
                'number': p.get('sweaterNumber'),
                'position': p.get('positionCode'),
                'gamesPlayed':       rs.get('gamesPlayed', 0),
                'goals':       rs.get('goals',       0),
                'assists':     rs.get('assists',     0),
                'points':      rs.get('points',      0),
                'playoffGames':   po.get('gamesPlayed', 0),
                'playoffGoals':   po.get('goals',       0),
                'playoffAssists': po.get('assists',     0),
                'playoffPoints':  po.get('points',      0),
            })

    # 3) look up the team’s logo from the same standings feed
    std = requests.get('https://api-web.nhle.com/v1/standings/now').json().get('standings', [])
    logo = next((t['teamLogo']
                 for t in std
                 if t['teamAbbrev']['default'] == team_abbrev), '')

    return jsonify({ 'logo': logo, 'players': players })

@app.route('/login')
def login():
    redirect_uri = url_for('authorize', _external=True)
    return github.authorize_redirect(redirect_uri)

@app.route('/authorize')
def authorize():
    token = github.authorize_access_token()
    resp  = github.get('user')
    profile = resp.json()
    session['user'] = {
        'id': profile['id'],
        'name': profile['login'],
        'avatar_url': profile.get('avatar_url')
    }
    return redirect(url_for('index'))


if __name__ == '__main__':
    app.run(debug=True)

@app.route('/robots.txt')
def robots_txt():
    return Response("User-agent: *\nDisallow:\n", mimetype="text/plain")

