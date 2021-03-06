#!/usr/bin/python

import os
import sys
import glob
import time
import json
import codecs
import urllib
import argparse
import sbconfig
import httplib2
import subprocess
import gdata.youtube
import gdata.youtube.service

user_email = sbconfig.user_email
user_password = sbconfig.user_password
dev_key = sbconfig.dev_key
refresh_rate = sbconfig.refresh_rate
max_simultaneous_dls = sbconfig.max_simultaneous_dls
queue_size = sbconfig.queue_size
download_dash = sbconfig.download_dash
use_custom_ffmpeg = sbconfig.use_custom_ffmpeg

yt_service = gdata.youtube.service.YouTubeService()
yt_service.ssl = True
yt_service.developer_key = dev_key
new_subscription_videos_uri = 'https://gdata.youtube.com/feeds/api/users/default/newsubscriptionvideos'
dldb = 'downloaded'
subdb = 'localsubs'

in_progress = []

def main():
	parser = argparse.ArgumentParser(description='YouTube subscription auto downloader command line options.')
	parser.add_argument('-s', '--skip-current-queue', action='store_true')
	parser.add_argument('-g', '--pull-subscriptions', action='store_true')
	parser.add_argument('-p', '--push-subscriptions', action='store_true')
	parser.add_argument('-I', '--run-once', action='store_true')
	parser.add_argument('-c', '--dont-check-subscriptions', action='store_true')
	parser.add_argument('-d', '--download-this')
	parser.add_argument('-z', '--dont-login', action='store_true')
	args = parser.parse_args()
	
	if not args.dont_login:
		login()
		
	check_files()
	
	if queue_size != 25:
		if queue_size <= 50 or queue_size >= 1:
			global new_subscription_videos_uri
			new_subscription_videos_uri += '?max-results=' + str(queue_size)
			
	if args.download_this:
		print "Single video mode."
		chosen_v, chosen_a, filename, ext = get_video_info(parse_id(args.download_this))
		download_video(chosen_v, chosen_a, filename, ext)
	
	if args.pull_subscriptions:
		print 'Grabbing remote subscriptions.'
		pull_subscribed_to()
	
	if args.push_subscriptions:
		print 'Adding local subscriptions.'
		push_subscribed_to()
	
	if args.skip_current_queue:
		print 'Skipping current subscription queue.'
		skip_current_queue()
		
	if args.dont_check_subscriptions:
		print 'Goodbye.'
		sys.exit(0)
	
	while True:
		check_files()
		check_and_download_subscriptions()
		
		if args.run_once:
			print 'Goodbye.'
			sys.exit(0)
		
		print 'Waiting', refresh_rate, 'seconds...';
		time.sleep(refresh_rate)
		
def check_files():
	if not os.path.exists(dldb):
		file(dldb, 'w').close()
	
	if not os.path.exists(subdb):
		file(subdb, 'w').close()

def pull_subscribed_to():
	subscription_feed = yt_service.GetYouTubeSubscriptionFeed('https://gdata.youtube.com/feeds/api/users/default/subscriptions?max-results=50')
	subscribed_to = [line.strip() for line in open(subdb)]
	total_subscriptions = int(subscription_feed.total_results.text)
	total_pages = total_subscriptions / 50
	
	for x in range(0, total_pages):
		if x > 0:
			try:
				subscription_feed = yt_service.GetYouTubeSubscriptionFeed('https://gdata.youtube.com/feeds/api/users/default/subscriptions?max-results=50&start-index=' + str(x * 50))
			except gdata.service.RequestError:
				return
				
		for entry in subscription_feed.entry:
			if entry.username.text not in subscribed_to:
				f = open(subdb,'a')
				f.write(entry.username.text + '\n')
				f.close()

def push_subscribed_to():
	subscription_feed = yt_service.GetYouTubeVideoFeed('https://gdata.youtube.com/feeds/api/users/default/subscriptions?max-results=50')
	subscribed_to_local = [line.strip() for line in open(subdb)]
	subscribed_to_remote = []
	total_subscriptions = int(subscription_feed.total_results.text)
	total_pages = total_subscriptions / 50
		
	for x in range(0, total_pages):
		if x > 0:
			try:
				subscription_feed = yt_service.GetYouTubeSubscriptionFeed('https://gdata.youtube.com/feeds/api/users/default/subscriptions?max-results=50&start-index=' + str(x * 50))
			except gdata.service.RequestError:
				break
				
		for entry in subscription_feed.entry:
			subscribed_to_remote.append(entry.username.text)
		
	for local_sub in subscribed_to_local:
		if local_sub not in subscribed_to_remote:
			new_subscription = yt_service.AddSubscriptionToChannel(
				username_to_subscribe_to=local_sub)
		
def skip_current_queue():
	ids = get_video_feed()
	downloaded = [line.strip() for line in open(dldb)]
	
	for video_id in ids:
		if video_id not in downloaded:
			f = open(dldb,'a')
			f.write(video_id + '\n')
			f.close()

def check_and_download_subscriptions():
	ids = get_video_feed()
	downloaded = [line.strip() for line in open(dldb)]
	
	for video_id in ids:
		if video_id not in in_progress and len(in_progress) < max_simultaneous_dls:
			if video_id not in downloaded:
				print "Retrieving video info..."
				chosen_v, chosen_a, filename, ext = get_video_info(video_id)
				download_video(chosen_v, chosen_a, filename, ext)
				
				f = open(dldb,'a')
				f.write(video_id + '\n')
				f.close()
				in_progress.remove(video_id)
				
def parse_id(url):
	return url[url.rfind('=') + 1:]

def get_video_info(video_id):
	d_v = ['264','137','136','135','133']
	d_a = ['141','140','139']
	v = ['22','18','5']
	ordered_v = ['264','137','22','136','135','18','133','5']
	chosen_v = ''
	chosen_a = ''
	ext = ''
	needs_a = 0
	in_progress.append(video_id)
	ytdl = subprocess.Popen(['youtube-dl', '-j', '--username', user_email, '--password', user_password, "https://www.youtube.com/watch?v={}".format(video_id)], stdout=subprocess.PIPE)
	out, err = ytdl.communicate()
	video_info = json.loads(out)
	
	for preferred in ordered_v:
		if len(chosen_v) > 0:
				break
		for available in video_info['formats']:
			if available['format_id'] == preferred:
				if preferred in d_v:
					if download_dash == 1:
						needs_a = 1
						chosen_v = available['url']
						ext = available['ext']
					else:
						break;
				else:
					chosen_v = available['url']
					ext = available['ext']
				break				
	
	if needs_a == 1:
		for preferred in d_a:
			if len(chosen_a) > 0:
				break
			for available in video_info['formats']:
				if available['format_id'] == preferred:
					chosen_a = available['url']
					break
					
	filename = u"{} - {} - {}".format(video_info['uploader'], video_info['title'], video_info['id'])
	for c in r'[]/\;,><&*:%=+@!#^()|?^':
		filename = filename.replace(c,'')
	
	return chosen_v, chosen_a, filename, ext

def download_video(v_url, a_url, filename, ext):
	if len(a_url) > 0:
		print u"Downloading {}".format(filename + '.mp4')
		if not os.path.exists(filename + '.m4v'):
			file(filename + '.m4v', 'w').close()
		urllib.urlretrieve(v_url, filename + '.m4v')
		
		if not os.path.exists(filename + '.m4a'):
			file(filename + '.m4a', 'w').close()	
		urllib.urlretrieve (a_url, filename + '.m4a')
		
		if use_custom_ffmpeg == 1:
			ffmpegarg = os.path.abspath('ffmpeg')
		else:
			ffmpegarg = 'ffmpeg'
		
		ffmpeg = subprocess.Popen([ffmpegarg, '-loglevel', 'quiet', '-i', filename + '.m4v' , '-i', filename + '.m4a', '-vcodec', 'copy', '-acodec', 'copy', filename + '.mp4'], stdout=subprocess.PIPE)
		out, err = ffmpeg.communicate()
		
		os.remove(filename + '.m4v');
		os.remove(filename + '.m4a');
	else:
		print u"Downloading '{}.{}'".format(filename, ext)
		if not os.path.exists(filename + '.' + ext):
			file(filename + '.' + ext, 'w').close()
		urllib.urlretrieve(v_url, filename + '.' + ext)
		
def login():
	print "Logging in to YouTube"
	yt_service.email = user_email
	yt_service.password = user_password
	yt_service.ProgrammaticLogin()
	
def get_video_feed():
	print "Retrieving subscription feed"
	ids = []
	feed = yt_service.GetYouTubeVideoFeed(new_subscription_videos_uri)
	for entry in feed.entry:
		gdata_video_url = entry.id.text
		video_id = entry.id.text[gdata_video_url.rfind('/') + 1:]
		ids.append(video_id)
		
	return ids
	
if __name__ == '__main__':
	main()
