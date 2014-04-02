# YouTube Playlist Bot
# Maintains a YouTube playlist that contains all submissions to a set of sub-reddits that are YouTube links

__author__ = 'Jon Minter (jdiminter@gmail.com)'
__version__ = '1.0a'

import time
import sqlite3
import praw
import gdata.youtube
import gdata.youtube.service
import settings
from pprint import pprint
import re

REDDIT_SUBMISSION_CATCHUP_LIMIT = 1000
REDDIT_SUBMISSION_LIMIT = 100
REDDIT_SUBMISSION_YOUTUBE_MEDIA_TYPE = 'youtube.com'
YOUTUBE_VIDEO_ID_REGEX_LIST = [
	re.compile(r'youtube(?:-nocookie)?\.com/watch[#\?].*?v=(?P<video_id>[^"\& ]+)'),
	re.compile(r'youtube(?:-nocookie)?\.com/embed/(?P<video_id>[^"\&\? ]+)'),
	re.compile(r'youtube(?:-nocookie)?\.com/v/(?P<video_id>[^"\&\? ]+)'),
	re.compile(r'youtube(?:-nocookie)?\.com/\?v=(?P<video_id>[^"\& ]+)'),
	re.compile(r'youtu\.be/(?P<video_id>[^"\&\? ]+)'),
	re.compile(r'gdata\.youtube\.com/feeds/api/videos/(?P<video_id>[^"\&\? ]+)')
]

def get_db_connection():
	db_connection = sqlite3.connect(settings.sqlite['filename'])
	
	#test to see if we need to run schema.sql
	result = db_connection.execute(settings.sqlite['create_schema_test'])
	if result.fetchone() is None:
		sql_schema = open('schema.sql').read()
		db_cursor = db_connection.cursor()
		db_cursor.executescript(sql_schema)
	return db_connection

def get_youtube_service():
	yt_service = gdata.youtube.service.YouTubeService()
	yt_service.ssl = True
	yt_service.email = settings.youtube['email']
	yt_service.password = settings.youtube['password']
	yt_service.source = settings.youtube['client_id']
	yt_service.developer_key = settings.youtube['developer_key']
	yt_service.client_id = settings.youtube['client_id']
	yt_service.ProgrammaticLogin()
	return yt_service

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

def get_youtube_video_id_from_url(url):
	for regex in YOUTUBE_VIDEO_ID_REGEX_LIST:
		match = regex.search(url)
		pprint(url)
		pprint(regex)
		pprint(match)
		if match:
			return match.group('video_id')


def run_bot():
	db_connection = get_db_connection()
	yt_service = get_youtube_service()
	r = praw.Reddit(settings.reddit['user_agent'])
	r.login(settings.reddit['username'], settings.reddit['password'])

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
							add_video_to_playlist(yt_service, settings.youtube['playlist_id'], youtube_video_id)
				else:
					print 'No media attribute'

				#db_connection.execute("INSERT INTO reddit_submissions_processed (submission_id, url) values (?,?)", (submission.id, submission.url))

		time.sleep(1800)

def get_youtube_oauth2_url():
	

