# frozen_string_literal: true

require 'rails_helper'

RSpec.describe YouTubeService, :regression, type: :service do
  let(:api_key) { 'test_youtube_api_key' }
  let(:service) { described_class.new(api_key: api_key) }

  describe 'exceptions hierarchy' do
    it 'defines proper custom exceptions inheriting from YouTubeService::Error' do
      expect(YouTubeService::Error).to be < StandardError
      expect(YouTubeService::NotConfigured).to be < YouTubeService::Error
      expect(YouTubeService::QuotaError).to be < YouTubeService::Error
      expect(YouTubeService::NotFoundError).to be < YouTubeService::Error
    end
  end

  describe 'configuration' do
    it 'raises NotConfigured when api key is not provided' do
      unconfigured = described_class.new(api_key: nil)
      expect { unconfigured.search('test') }.to raise_error(YouTubeService::NotConfigured)
      expect { unconfigured.video_metadata('xyz123') }.to raise_error(YouTubeService::NotConfigured)
      expect { unconfigured.channel_info('UC123') }.to raise_error(YouTubeService::NotConfigured)
    end
  end

  describe '#search' do
    it 'raises ArgumentError if query is blank' do
      expect { service.search('') }.to raise_error(ArgumentError)
      expect { service.search('   ') }.to raise_error(ArgumentError)
    end

    it 'searches youtube videos and parses the response' do
      stub_request(:get, 'https://www.googleapis.com/youtube/v3/search')
        .with(query: hash_including({ 'q' => 'ruby on rails', 'part' => 'snippet', 'type' => 'video', 'key' => api_key }))
        .to_return(
          status: 200,
          headers: { 'Content-Type' => 'application/json' },
          body: {
            items: [
              {
                id: { videoId: 'vid_123' },
                snippet: {
                  title: 'Rails 8 Tutorial',
                  channelTitle: 'RubyDev',
                  channelId: 'UC_dev_1',
                  publishedAt: '2026-01-01T12:00:00Z',
                  thumbnails: { default: { url: 'https://img.youtube.com/vi/vid_123/default.jpg' } }
                }
              }
            ]
          }.to_json
        )

      results = service.search('ruby on rails', max_results: 10)
      expect(results).to be_an(Array)
      expect(results.length).to eq(1)
      expect(results.first[:video_id]).to eq('vid_123')
      expect(results.first[:title]).to eq('Rails 8 Tutorial')
      expect(results.first[:channel_title]).to eq('RubyDev')
      expect(results.first[:channel_id]).to eq('UC_dev_1')
      expect(results.first[:published_at]).to eq('2026-01-01T12:00:00Z')
      expect(results.first[:thumbnail]).to eq('https://img.youtube.com/vi/vid_123/default.jpg')
    end

    it 'clamps max_results between 1 and 50' do
      stub = stub_request(:get, 'https://www.googleapis.com/youtube/v3/search')
             .with(query: hash_including({ 'maxResults' => '50' }))
             .to_return(status: 200, body: { items: [] }.to_json, headers: { 'Content-Type' => 'application/json' })

      service.search('test', max_results: 100)
      expect(stub).to have_been_requested

      stub_min = stub_request(:get, 'https://www.googleapis.com/youtube/v3/search')
                 .with(query: hash_including({ 'maxResults' => '1' }))
                 .to_return(status: 200, body: { items: [] }.to_json, headers: { 'Content-Type' => 'application/json' })

      service.search('test', max_results: -5)
      expect(stub_min).to have_been_requested
    end

    it 'raises QuotaError on 403 quotaExceeded error' do
      stub_request(:get, 'https://www.googleapis.com/youtube/v3/search')
        .with(query: hash_including({ 'q' => 'quota_test' }))
        .to_return(
          status: 403,
          headers: { 'Content-Type' => 'application/json' },
          body: {
            error: {
              errors: [ { reason: 'quotaExceeded', message: 'Quota exceeded' } ]
            }
          }.to_json
        )

      expect { service.search('quota_test') }.to raise_error(YouTubeService::QuotaError)
    end

    it 'handles Faraday::TimeoutError' do
      stub_request(:get, 'https://www.googleapis.com/youtube/v3/search')
        .with(query: hash_including({ 'q' => 'timeout_test' }))
        .to_timeout

      expect { service.search('timeout_test') }.to raise_error(Faraday::TimeoutError)
    end
  end

  describe '#video_metadata' do
    let(:video_payload) do
      {
        items: [
          {
            id: 'dQw4w9WgXcQ',
            snippet: {
              title: 'Never Gonna Give You Up',
              description: 'Official music video',
              channelTitle: 'Rick Astley',
              channelId: 'UCuAXFkgsw1L7xaCfnd5JJOw',
              publishedAt: '2009-10-25T06:57:33Z',
              thumbnails: { default: { url: 'https://i.ytimg.com/vi/dQw4w9WgXcQ/default.jpg' } }
            },
            contentDetails: {
              duration: 'PT3M33S'
            },
            statistics: {
              viewCount: '1500000000',
              likeCount: '17000000',
              commentCount: '2500000'
            }
          }
        ]
      }
    end

    it 'fetches metadata with a video ID' do
      stub_request(:get, 'https://www.googleapis.com/youtube/v3/videos')
        .with(query: hash_including({ 'id' => 'dQw4w9WgXcQ', 'part' => 'snippet,contentDetails,statistics', 'key' => api_key }))
        .to_return(status: 200, headers: { 'Content-Type' => 'application/json' }, body: video_payload.to_json)

      data = service.video_metadata('dQw4w9WgXcQ')
      expect(data[:video_id]).to eq('dQw4w9WgXcQ')
      expect(data[:title]).to eq('Never Gonna Give You Up')
      expect(data[:duration_iso]).to eq('PT3M33S')
      expect(data[:duration_seconds]).to eq(213)
      expect(data[:view_count]).to eq(1500000000)
      expect(data[:like_count]).to eq(17000000)
      expect(data[:comment_count]).to eq(2500000)
      expect(data[:channel_title]).to eq('Rick Astley')
    end

    it 'extracts video ID from a YouTube watch URL' do
      stub_request(:get, 'https://www.googleapis.com/youtube/v3/videos')
        .with(query: hash_including({ 'id' => 'dQw4w9WgXcQ' }))
        .to_return(status: 200, headers: { 'Content-Type' => 'application/json' }, body: video_payload.to_json)

      data = service.video_metadata('https://www.youtube.com/watch?v=dQw4w9WgXcQ')
      expect(data[:video_id]).to eq('dQw4w9WgXcQ')
    end

    it 'extracts video ID from a youtu.be short URL' do
      stub_request(:get, 'https://www.googleapis.com/youtube/v3/videos')
        .with(query: hash_including({ 'id' => 'dQw4w9WgXcQ' }))
        .to_return(status: 200, headers: { 'Content-Type' => 'application/json' }, body: video_payload.to_json)

      data = service.video_metadata('https://youtu.be/dQw4w9WgXcQ')
      expect(data[:video_id]).to eq('dQw4w9WgXcQ')
    end

    it 'extracts video ID from a YouTube shorts URL' do
      stub_request(:get, %r{\Ahttps://www.googleapis.com/youtube/v3/videos})
        .with(query: hash_including({ 'id' => 'dQw4w9WgXcQ' }))
        .to_return(status: 200, headers: { 'Content-Type' => 'application/json' }, body: video_payload.to_json)

      data = service.video_metadata('https://www.youtube.com/shorts/dQw4w9WgXcQ')
      expect(data[:video_id]).to eq('dQw4w9WgXcQ')
    end

    it 'raises ArgumentError when video_id is blank' do
      expect { service.video_metadata('') }.to raise_error(ArgumentError)
      expect { service.video_metadata('   ') }.to raise_error(ArgumentError)
    end

    it 'raises NotFoundError when video is not found' do
      stub_request(:get, 'https://www.googleapis.com/youtube/v3/videos')
        .with(query: hash_including({ 'id' => 'missing_id' }))
        .to_return(status: 200, headers: { 'Content-Type' => 'application/json' }, body: { items: [] }.to_json)

      expect { service.video_metadata('missing_id') }.to raise_error(YouTubeService::NotFoundError)
    end

    it 'raises QuotaError on 403 quota error' do
      stub_request(:get, %r{\Ahttps://www.googleapis.com/youtube/v3/videos})
        .to_return(
          status: 403,
          headers: { 'Content-Type' => 'application/json' },
          body: { error: { errors: [ { reason: 'quotaExceeded', message: 'Quota exceeded' } ] } }.to_json
        )

      expect { service.video_metadata('dQw4w9WgXcQ') }.to raise_error(YouTubeService::QuotaError)
    end

    it 'raises Error on non-quota 403 response' do
      stub_request(:get, %r{\Ahttps://www.googleapis.com/youtube/v3/videos})
        .to_return(status: 403, headers: { 'Content-Type' => 'application/json' }, body: { error: { message: 'Forbidden' } }.to_json)

      expect { service.video_metadata('dQw4w9WgXcQ') }.to raise_error(YouTubeService::Error, /forbidden/)
    end

    it 'raises NotFoundError on 404 response' do
      stub_request(:get, %r{\Ahttps://www.googleapis.com/youtube/v3/videos})
        .to_return(status: 404, headers: { 'Content-Type' => 'application/json' }, body: 'Not Found')

      expect { service.video_metadata('dQw4w9WgXcQ') }.to raise_error(YouTubeService::NotFoundError)
    end

    it 'raises Error on 500 error' do
      stub_request(:get, %r{\Ahttps://www.googleapis.com/youtube/v3/videos})
        .to_return(status: 500, headers: { 'Content-Type' => 'application/json' }, body: 'Internal Error')

      expect { service.video_metadata('dQw4w9WgXcQ') }.to raise_error(YouTubeService::Error, /HTTP 500/)
    end

    it 'raises Error when response body is not valid JSON' do
      stub_request(:get, %r{\Ahttps://www.googleapis.com/youtube/v3/videos})
        .to_return(status: 200, headers: { 'Content-Type' => 'application/json' }, body: 'invalid json')

      expect { service.video_metadata('dQw4w9WgXcQ') }.to raise_error(YouTubeService::Error, /Failed to parse/)
    end
  end

  describe '#channel_info' do
    let(:channel_payload) do
      {
        items: [
          {
            id: 'UCuAXFkgsw1L7xaCfnd5JJOw',
            snippet: {
              title: 'Rick Astley',
              description: 'Official Rick Astley Channel',
              customUrl: '@rickastley',
              publishedAt: '2006-10-18T20:00:00Z',
              thumbnails: { default: { url: 'https://yt3.ggpht.com/default.jpg' } }
            },
            contentDetails: {
              relatedPlaylists: { uploads: 'UUuAXFkgsw1L7xaCfnd5JJOw' }
            },
            statistics: {
              viewCount: '2000000000',
              subscriberCount: '3500000',
              videoCount: '120'
            }
          }
        ]
      }
    end

    it 'raises ArgumentError when channel_id_or_handle is blank' do
      expect { service.channel_info('') }.to raise_error(ArgumentError)
      expect { service.channel_info('   ') }.to raise_error(ArgumentError)
    end

    it 'fetches channel info using channel ID' do
      stub_request(:get, 'https://www.googleapis.com/youtube/v3/channels')
        .with(query: hash_including({ 'id' => 'UCuAXFkgsw1L7xaCfnd5JJOw', 'part' => 'snippet,statistics,contentDetails', 'key' => api_key }))
        .to_return(status: 200, headers: { 'Content-Type' => 'application/json' }, body: channel_payload.to_json)

      info = service.channel_info('UCuAXFkgsw1L7xaCfnd5JJOw')
      expect(info[:channel_id]).to eq('UCuAXFkgsw1L7xaCfnd5JJOw')
      expect(info[:title]).to eq('Rick Astley')
      expect(info[:subscriber_count]).to eq(3500000)
      expect(info[:uploads_playlist_id]).to eq('UUuAXFkgsw1L7xaCfnd5JJOw')
    end

    it 'fetches channel info using handle' do
      stub_request(:get, 'https://www.googleapis.com/youtube/v3/channels')
        .with(query: hash_including({ 'forHandle' => '@rickastley' }))
        .to_return(status: 200, headers: { 'Content-Type' => 'application/json' }, body: channel_payload.to_json)

      info = service.channel_info('@rickastley')
      expect(info[:channel_id]).to eq('UCuAXFkgsw1L7xaCfnd5JJOw')
      expect(info[:title]).to eq('Rick Astley')
    end

    it 'raises NotFoundError when channel is not found' do
      stub_request(:get, %r{\Ahttps://www.googleapis.com/youtube/v3/channels})
        .to_return(status: 200, headers: { 'Content-Type' => 'application/json' }, body: { items: [] }.to_json)

      expect { service.channel_info('UC_nonexistent') }.to raise_error(YouTubeService::NotFoundError)
    end
  end

  describe '#parse_iso8601_duration' do
    it 'parses ISO 8601 durations correctly' do
      expect(service.parse_iso8601_duration('PT1H2M3S')).to eq(3723)
      expect(service.parse_iso8601_duration('PT2H')).to eq(7200)
      expect(service.parse_iso8601_duration('PT15M')).to eq(900)
      expect(service.parse_iso8601_duration('PT45S')).to eq(45)
      expect(service.parse_iso8601_duration('PT1H30S')).to eq(3630)
      expect(service.parse_iso8601_duration('PT0S')).to eq(0)
    end

    it 'returns 0 for invalid or empty duration strings' do
      expect(service.parse_iso8601_duration('invalid')).to eq(0)
      expect(service.parse_iso8601_duration('')).to eq(0)
      expect(service.parse_iso8601_duration(nil)).to eq(0)
      expect(service.parse_iso8601_duration('1H2M3S')).to eq(0)
    end
  end

  describe '#quota_usage' do
    it 'returns used, limit, and reset_at structure' do
      quota = service.quota_usage
      expect(quota).to have_key(:used)
      expect(quota).to have_key(:limit)
      expect(quota).to have_key(:reset_at)
      expect(quota[:limit]).to eq(10000)
      expect(quota[:used]).to be_a(Integer)
      expect(quota[:reset_at]).to match(/\A\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}/)
    end

    it 'tracks quota increments when search is called' do
      stub_request(:get, 'https://www.googleapis.com/youtube/v3/search')
        .with(query: hash_including({ 'q' => 'quota_tracker' }))
        .to_return(status: 200, headers: { 'Content-Type' => 'application/json' }, body: { items: [] }.to_json)

      before_used = service.quota_usage[:used]
      service.search('quota_tracker')
      after_used = service.quota_usage[:used]
      expect(after_used).to eq(before_used + 100)
    end
  end
end
