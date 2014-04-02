# YouTube Playlist Bot
# Maintains a YouTube playlist that contains all submissions to a set of sub-reddits that are YouTube links

__author__ = 'Jon Minter (jdiminter@gmail.com)'
__version__ = '1.0a'

import os
import sys
import time
import sqlite3
import praw
import gdata.gauth
import gdata.youtube
import gdata.youtube.service
import settings
import urllib
from pprint import pprint
import re

SCRIPT_NAME = os.path.basename(__file__)
SQLITE_FILENAME = 'youtubeplaylistbot.db',
SQLITE_CREATE_SCHEMA_TEST = "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='reddit_submissions_processed'"
REDDIT_USER_AGENT = 'YoutubePlaylistBot by /u/codeninja84 v 1.0a https://github.com/jonminter/youtubeplaylistbot'
REDDIT_SUBMISSION_CATCHUP_LIMIT = 1000
REDDIT_SUBMISSION_LIMIT = 100
REDDIT_SUBMISSION_YOUTUBE_MEDIA_TYPE = 'youtube.com'
GOOGLE_USER_AGENT = 'Reddit YoutubePlaylistBot'
GOOGLE_OAUTH_URL = 'https://accounts.google.com/o/oauth2/auth'
GOOGLE_OAUTH_REDIRECT_URI = 'urn:ietf:wg:oauth:2.0:oob'
GOOGLE_OAUTH_SCOPE = 'https://www.googleapis.com/auth/youtube'
GOOGLE_OAUTH_TOKEN_VARIABLE = 'gdata_oauth2_token'
YOUTUBE_VIDEO_ID_REGEX_LIST = [
	re.compile(r'youtube(?:-nocookie)?\.com/watch[#\?].*?v=(?P<video_id>[^"\& ]+)'),
	re.compile(r'youtube(?:-nocookie)?\.com/embed/(?P<video_id>[^"\&\? ]+)'),
	re.compile(r'youtube(?:-nocookie)?\.com/v/(?P<video_id>[^"\&\? ]+)'),
	re.compile(r'youtube(?:-nocookie)?\.com/\?v=(?P<video_id>[^"\& ]+)'),
	re.compile(r'youtu\.be/(?P<video_id>[^"\&\? ]+)'),
	re.compile(r'gdata\.youtube\.com/feeds/api/videos/(?P<video_id>[^"\&\? ]+)')
]

# Opens the connection to the SQLite3 database and tests to see if the schema needs to be
# created or updated and performs queries to update the schema if neccessary
def get_db_connection():
	db_connection = sqlite3.connect(SQLITE_FILENAME)
	
	#test to see if we need to run schema.sql
	result = db_connection.execute(SQLITE_CREATE_SCHEMA_TEST)
	if result.fetchone() is None:
		sql_schema = open('schema.sql').read()
		db_cursor = db_connection.cursor()
		db_cursor.executescript(sql_schema)
	return db_connection

# Retrieves a session auth token for GData services
def get_gdata_auth_token():
	token = gdata.gauth.OAuth2Token(
		client_id=settings.google['oauth2']['client_id'],
		client_secret=settings.google['oauth2']['client_secret'], 
		scope=GOOGLE_OAUTH_SCOPE,
		user_agent='application-name-goes-here')
	return token

def get_gdata_saved_auth_token(db_connection):
	sql_result = db_connection.execute('SELECT value FROM config_variables WHERE name=?', (GOOGLE_OAUTH_TOKEN_VARIABLE,))
	token_row = sql_result.fetchone()
	if token_row is None:
		raise Exception('No auth token stored')
	token = gdata.gauth.token_from_blob(token_row[0])
	return token

# Retrieves an instance of the YouTube Data API service object
def get_youtube_service(auth_token):
	yt_service = gdata.youtube.service.YouTubeService()
	yt_service.ssl = True
	auth_token.authorize(yt_service)
	return yt_service

# Adds the specified video to the playlist using the YouTube Data API object
def add_video_to_playlist(yt_service, playlist_id, video_id):
	pprint(yt_service)
	add_video_request=yt_service.playlistItems.insert(
		part="snippet",
		body={
			'snippet': {
				'playlistId': playlist_id, 
				'resourceId': {
					'kind': 'youtube#video',
					'videoId': video_id
				}
				#'position': 0
			}
		}
	).execute()
	return add_video_request

# Parses a YouTube URL and retrieves the Video ID from that URL.
# Uses a set of regular expressions to parse many different forms of YouTube video URLs.
def get_youtube_video_id_from_url(url):
	for regex in YOUTUBE_VIDEO_ID_REGEX_LIST:
		match = regex.search(url)
		pprint(url)
		pprint(regex)
		pprint(match)
		if match:
			return match.group('video_id')

# Method to run the logic for the bot. Connects to the Reddit API and periodically polls the API to get the latest submissions to the subreddits
# that the bot is watching. It loops through those submissions and for the ones that have not been processed yet if they are links to youtube
# it adds the videos to a playlist.
def run_bot(args):
	db_connection = get_db_connection()
	auth_token = get_gdata_saved_auth_token(db_connection)
	yt_service = get_youtube_service(auth_token)
	print "About to login to reddit!"
	r = praw.Reddit(REDDIT_USER_AGENT)
	r.login(settings.reddit['username'], settings.reddit['password'])
	print "Logged into reddit!"
	while True:
		multireddit = '+'.join(settings.reddit['subreddits'])
		subreddit = r.get_subreddit(multireddit)
		for submission in subreddit.get_new(limit=100):
			
			sql_result = db_connection.execute('SELECT COUNT(submission_id) FROM reddit_submissions_processed WHERE submission_id = ?', (submission.id,))
			submission_processed = sql_result.fetchone()
			print submission.url
			if submission_processed[0] == 0:
				print 'Submission not processed'
				if submission.media:
					print submission.media['type']
					if submission.media['type'] == REDDIT_SUBMISSION_YOUTUBE_MEDIA_TYPE:
						youtube_video_id = get_youtube_video_id_from_url(submission.url)
						print 'YouTube Video ID: ', youtube_video_id
						if youtube_video_id:
							add_video_to_playlist(yt_service, settings.google['youtube']['playlist_id'], youtube_video_id)
				else:
					print 'No media attribute'

				#db_connection.execute("INSERT INTO reddit_submissions_processed (submission_id, url) values (?,?)", (submission.id, submission.url))
		#db_connection.commit()

		time.sleep(1800)

# Returns a URL to use to get a long lived OAuth2 token from Google's authentication web services
def print_youtube_oauth2_url(args):
	token = get_gdata_auth_token()
	oauth2_url = token.generate_authorize_url(redirect_uri=GOOGLE_OAUTH_REDIRECT_URI)
	print oauth2_url

def store_auth_token(args):
	token = get_gdata_auth_token()

	if len(args) >= 2:
		code = args[2]
		token.redirect_uri = GOOGLE_OAUTH_REDIRECT_URI
		token.get_access_token(code)
		token_blob = gdata.gauth.token_to_blob(token)

		db_connection = get_db_connection()
		db_connection.execute('INSERT INTO config_variables (name, value) values (?,?)', (GOOGLE_OAUTH_TOKEN_VARIABLE, token_blob))
		db_connection.commit()
	else:
		print "Requires a 2nd argument with the authentication code from google, i.e. 'python youtubeplaylistbot.py set_auth_code [CODE GOES HERE]"

def print_help(args):
	print "Takes one command line argument: runbot or authenticate"


# Main logic for program
commandMap = {
	'runbot': run_bot,
	'get_auth_url': print_youtube_oauth2_url,
	'set_auth_code': store_auth_token,
	'help': print_help,
}
if len(sys.argv) > 1:
	command = sys.argv[1].strip()
	try:
		commandMap[command](sys.argv)
	except KeyError:
		print ''.join(["Invalid argument '", command, "'"])
		print_help([])
else:
	print_help([])