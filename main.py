import json
import logging

import os
import boto3
import shortuuid
from flask import Flask, request, Request, jsonify, Response, redirect, url_for
from flask_cors import CORS
from flask_cors.decorator import LOG
from flask_dance.contrib.google import make_google_blueprint, google

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

app.secret_key = os.environ.get("FLASK_SECRET_KEY", "supersekrit")
app.config["GOOGLE_OAUTH_CLIENT_ID"] = os.environ.get("GOOGLE_OAUTH_CLIENT_ID")
app.config["GOOGLE_OAUTH_CLIENT_SECRET"] = os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET")
google_bp = make_google_blueprint(
	scope="https://www.googleapis.com/auth/userinfo.profile https://www.googleapis.com/auth/userinfo.email",
	redirect_url='https://jhxwb4ferb.execute-api.us-west-2.amazonaws.com/prod/login'
	#redirect_to='login'
)
app.register_blueprint(google_bp, url_prefix="/login")

def valid_redirect(url: str) -> bool:
	return url and any(url.startswith(allowed_url) for allowed_url in WHITELIST)

@app.route("/login")
def login():
	if not google.authorized:
		r = redirect(url_for("google.login"))
		if valid_redirect(request.args.get('redirect')):
			r.set_cookie('redirect', request.args['redirect'])
		return r
	elif valid_redirect(request.cookies.get('redirect')):
		r = redirect(request.cookies['redirect'])
		r.set_cookie('redirect', '')
		return r
	elif valid_redirect(request.args.get('redirect')):
		return redirect(request.args['redirect'])
	else:
		resp = google.get("/oauth2/v1/userinfo")
		assert resp.ok, resp.text
		return "You are {email} on Google".format(email=resp.json()["email"])

@app.route('/')
def root():
	if 'name' in request.args:
		return f'Hi {request.args["name"]}'
	else:
		return f'Greetings stranger. You suck'

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

	owner = 'public'
	if google.authorized:
		try:
			resp = google.get("/oauth2/v1/userinfo")
			assert resp.ok, resp.text
			# monsters.append({
			# 	'name': f'YOU were the biggest monster of them all, {resp.json()["email"]}'
			# })
			owner = resp.json()["email"]
		except:
			pass
	# if user not logged in, give them public monsters
	# if user is logged in, give them all monsters with their email as well
	for monster in Monster.scan(Monster.owner == owner):
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

	owner = 'public'
	if google.authorized:
		try:
			resp = google.get("/oauth2/v1/userinfo")
			assert resp.ok, resp.text
			owner = resp.json()["email"]
		except:
			pass

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