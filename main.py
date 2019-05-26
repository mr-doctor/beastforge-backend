import json
import logging

import boto3
import shortuuid
from flask import Flask, request, Request, jsonify, Response
from flask_cors import CORS
from flask_cors.decorator import LOG

from model import Monster

MONSTERS_BUCKET = 'the-beastforge-monsters'
DATA_URL = 'https://the-beastforge-monsters.s3-us-west-2.amazonaws.com/'

app = Flask(__name__)
CORS(
	app,
	origins=[
		'http://127.0.0.1:3000',
		'http://localhost:3000',
		'https://drcnbgf9z5dx1.cloudfront.net'
	],
	supports_credentials=True,
	vary_header=True
)

client = boto3.client('s3')

request: Request = request

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
	for monster in Monster.scan():
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

	monster_id = shortuuid.uuid()
	monster = Monster(id=monster_id, name=name)
	monster.save()

	key = f'{monster_id}.json'
	print('Saving to', key)
	client.put_object(
		Bucket=MONSTERS_BUCKET,
		Key=key,
		Body=json.dumps(request.json, indent=1).encode(),
		ContentType='application/json',
		ACL='public-read'
	)
	return jsonify(monster_id=monster_id, key=key)



logging.basicConfig(level=logging.INFO)
LOG.setLevel(logging.INFO)