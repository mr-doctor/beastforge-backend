import json
import logging

import os
from typing import Optional

import boto3
import shortuuid
from flask import Flask, request, Request, jsonify, Response, redirect, url_for
from flask_cors import CORS
from flask_cors.decorator import LOG
from flask_dance.contrib.google import make_google_blueprint, google
from oauthlib.oauth2 import InvalidGrantError, TokenExpiredError
import jwt
import datetime

from model import Monster

MONSTERS_BUCKET = 'the-beastforge-monsters'
DATA_URL = 'https://the-beastforge-monsters.s3-us-west-2.amazonaws.com/'
WHITELIST = [
		'http://127.0.0.1:3000',
		'http://localhost:3000',
		'http://the-beastforge.s3-website-us-west-2.amazonaws.com',
		'https://the-beastforge.s3-website-us-west-2.amazonaws.com',
		'https://drcnbgf9z5dx1.cloudfront.net'
	]


app = Flask(__name__)
CORS(
	app,
	origins=WHITELIST,
	supports_credentials=True,
	vary_header=True
)

client = boto3.client('s3')

request: Request = request

logger = logging.getLogger(__name__)

app.config['JWT_SECRET_KEY'] = os.environ.get('JWT_SECRET_KEY')

app.secret_key = os.environ.get("FLASK_SECRET_KEY", "supersekrit")
app.config["GOOGLE_OAUTH_CLIENT_ID"] = os.environ.get("GOOGLE_OAUTH_CLIENT_ID")
app.config["GOOGLE_OAUTH_CLIENT_SECRET"] = os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET")
if bool(os.environ.get('FLASK_DEBUG')):
	google_bp = make_google_blueprint(
		scope="https://www.googleapis.com/auth/userinfo.profile https://www.googleapis.com/auth/userinfo.email",
		redirect_to='login'
	)
else:
	google_bp = make_google_blueprint(
		scope="https://www.googleapis.com/auth/userinfo.profile https://www.googleapis.com/auth/userinfo.email",
		redirect_url='https://jhxwb4ferb.execute-api.us-west-2.amazonaws.com/prod/login'
	)
app.register_blueprint(google_bp, url_prefix="/login")

def valid_redirect(url: str) -> bool:
	return url and any(url.startswith(allowed_url) for allowed_url in WHITELIST)

@app.route("/login")
def login():
	if google.authorized:
		try:
			resp = google.get("/oauth2/v1/userinfo")
			assert resp.ok, resp.text
		except:
			require_login = True
		else:
			require_login = False
	else:
		require_login = True

	if require_login:
		r = redirect(url_for("google.login"))
		if valid_redirect(request.args.get('redirect')):
			r.set_cookie('redirect', request.args['redirect'])
		return r
	else:
		if valid_redirect(request.cookies.get('redirect')):
			# user just logged in
			# they were redirected here *from google*, which they were redirected to from flask dance,
			# which they were redirected to from /login. When they visited /login, then provided ?redirect=...
			# and this was transferred to a redirect cookie
			r = redirect(request.cookies['redirect'])
			r.set_cookie('redirect', '')
		elif valid_redirect(request.args.get('redirect')):
			# user already logged in and oauth valid
			# they have logged in before, and their OAUTH token was still valid to fetch their email
			r = redirect(request.args['redirect'])
		else:
			# already logged in or just logged in, no valid redirect (usually shouldn't get here)
			r = Response(response="You are {email} on Google".format(email=resp.json()["email"]))

		user_jwt = jwt.encode(
			{
				'email': resp.json()["email"],
				'exp': datetime.datetime.utcnow() + datetime.timedelta(days=8),
			},
			app.config['JWT_SECRET_KEY']
		)
		r.set_cookie('user', user_jwt, max_age=7 * 24 * 60)

		return r


def get_email() -> Optional[str]:
	user_jwt = request.cookies.get('user')
	try:
		return jwt.decode(user_jwt, app.config['JWT_SECRET_KEY'])['email']
	except Exception as e:
		logger.warning(f'Failed to decode JWT {user_jwt}: {e}')
		return None


@app.route('/')
def root():
	email = get_email()
	if email:
		return f'Hi {email}'
	else:
		return Response(status=401, response='You are not logged in')

# @app.route('/monster/<monster_id>')
# def monster(monster_id: str):
# 	with open('monster.json') as f:
# 		monster_data = json.load(f)
# 	return Response(
# 		response=json.dumps(monster_data),
# 		status=200,
# 		mimetype='application/json'
# 	)

@app.route('/list_monsters')
def list_monsters():
	monsters = []

	owner = get_email()

	filter = Monster.public == True
	if owner:
		filter |= Monster.owner == owner

	for monster in Monster.scan(filter):
		monsters.append({
			'name': monster.name,
			'monster_id': monster.id
		})
	return jsonify(monsters=monsters)

@app.route('/list_monsters_s3')
def list_monsters_s3():
	objects = client.list_objects_v2(
		Bucket=MONSTERS_BUCKET
	)
	monsters = []
	for object in objects['Contents']:
		key = object['Key']
		monster_data = json.loads(client.get_object(
			Bucket=MONSTERS_BUCKET,
			Key=key
		)['Body'].read().decode())
		monsters.append({
			'name': monster_data['monsterName'],
			'monster_id': key.split('.')[0]
		})
	return jsonify(monsters=monsters)

@app.route('/save_monster', methods=['POST'])
def save_monster():
	name = request.json['monsterName']
	if not name:
		return Response(status=400, response=json.dumps({'error': 'Must have a name'}))
	owner = get_email()
	if not owner:
		return Response(status=401, response="Not logged in")

	monster_id = shortuuid.uuid()
	print(owner)
	monster = Monster(id=monster_id, name=name, owner=owner)
	monster.save()

	key = f'{monster_id}.json'
	print('Saving to', key)
	data = json.dumps(request.json, indent=1).encode()
	if len(data) > 10 * 1024:
		# over 10kb
		return Response(status=400)
	client.put_object(
		Bucket=MONSTERS_BUCKET,
		Key=key,
		Body=data,
		ContentType='application/json',
		ACL='public-read'
	)
	return jsonify(monster_id=monster_id, key=key)



logging.basicConfig(level=logging.INFO)
LOG.setLevel(logging.INFO)