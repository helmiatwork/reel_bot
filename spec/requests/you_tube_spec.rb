# frozen_string_literal: true

require 'rails_helper'

RSpec.describe 'YouTube', :regression, type: :request do
  let(:mock_service) { instance_double(YouTubeService) }

  before do
    allow(YouTubeService).to receive(:new).and_return(mock_service)
  end

  describe 'GET /youtube/search' do
    it 'returns 200 with search results when service succeeds' do
      results = [
        {
          video_id: 'vid_123',
          title: 'Sample Video',
          channel_title: 'Sample Channel',
          channel_id: 'UC123',
          published_at: '2026-01-01T00:00:00Z',
          thumbnail: 'https://example.com/thumb.jpg'
        }
      ]
      allow(mock_service).to receive(:search).with('tech reels', max_results: 10).and_return(results)

      get '/youtube/search', params: { q: 'tech reels', max_results: 10 }

      expect(response).to have_http_status(:ok)
      json = JSON.parse(response.body)
      expect(json).to be_an(Array)
      expect(json.first['video_id']).to eq('vid_123')
      expect(json.first['title']).to eq('Sample Video')
    end

    it 'accepts query parameter instead of q' do
      allow(mock_service).to receive(:search).with('tech reels', max_results: 50).and_return([])

      get '/youtube/search', params: { query: 'tech reels' }

      expect(response).to have_http_status(:ok)
    end

    it 'returns 400 Bad Request if query param is missing or blank' do
      get '/youtube/search'
      expect(response).to have_http_status(:bad_request)
      json = JSON.parse(response.body)
      expect(json['error']).to be_present
    end
  end

  describe 'GET /youtube/video/:id' do
    it 'returns 200 with video metadata when found' do
      metadata = {
        video_id: 'dQw4w9WgXcQ',
        title: 'Never Gonna Give You Up',
        duration_iso: 'PT3M33S',
        duration_seconds: 213,
        view_count: 1500000000
      }
      allow(mock_service).to receive(:video_metadata).with('dQw4w9WgXcQ').and_return(metadata)

      get '/youtube/video/dQw4w9WgXcQ'

      expect(response).to have_http_status(:ok)
      json = JSON.parse(response.body)
      expect(json['video_id']).to eq('dQw4w9WgXcQ')
      expect(json['title']).to eq('Never Gonna Give You Up')
    end

    it 'returns 404 when video is not found' do
      allow(mock_service).to receive(:video_metadata).with('nonexistent_id')
        .and_raise(YouTubeService::NotFoundError.new('Video not found'))

      get '/youtube/video/nonexistent_id'

      expect(response).to have_http_status(:not_found)
      json = JSON.parse(response.body)
      expect(json['error']).to include('Video not found')
    end
  end

  describe 'GET /youtube/channel/:id' do
    it 'returns 200 with channel info when found' do
      info = {
        channel_id: 'UC1234567890',
        title: 'Tech Channel',
        subscriber_count: 50000
      }
      allow(mock_service).to receive(:channel_info).with('UC1234567890').and_return(info)

      get '/youtube/channel/UC1234567890'

      expect(response).to have_http_status(:ok)
      json = JSON.parse(response.body)
      expect(json['channel_id']).to eq('UC1234567890')
      expect(json['title']).to eq('Tech Channel')
    end

    it 'returns 404 when channel is not found' do
      allow(mock_service).to receive(:channel_info).with('missing_channel')
        .and_raise(YouTubeService::NotFoundError.new('Channel not found'))

      get '/youtube/channel/missing_channel'

      expect(response).to have_http_status(:not_found)
      json = JSON.parse(response.body)
      expect(json['error']).to include('Channel not found')
    end
  end

  describe 'GET /youtube/quota' do
    it 'returns 200 with quota usage' do
      quota_data = {
        used: 120,
        limit: 10000,
        reset_at: '2026-09-13T00:00:00Z'
      }
      allow(mock_service).to receive(:quota_usage).and_return(quota_data)

      get '/youtube/quota'

      expect(response).to have_http_status(:ok)
      json = JSON.parse(response.body)
      expect(json['used']).to eq(120)
      expect(json['limit']).to eq(10000)
      expect(json['reset_at']).to eq('2026-09-13T00:00:00Z')
    end
  end

  describe 'error handling across endpoints' do
    it 'rescues YouTubeService::NotConfigured and responds with 401 Unauthorized' do
      allow(mock_service).to receive(:search)
        .and_raise(YouTubeService::NotConfigured.new('YOUTUBE_API_KEY not configured'))

      get '/youtube/search', params: { q: 'fail_key' }

      expect(response).to have_http_status(:unauthorized)
      json = JSON.parse(response.body)
      expect(json['error']).to include('not configured')
    end

    it 'rescues YouTubeService::QuotaError and responds with 429 Too Many Requests' do
      allow(mock_service).to receive(:video_metadata)
        .and_raise(YouTubeService::QuotaError.new('YouTube API quota exceeded'))

      get '/youtube/video/dQw4w9WgXcQ'

      expect(response).to have_http_status(:too_many_requests)
      json = JSON.parse(response.body)
      expect(json['error']).to include('quota exceeded')
    end

    it 'rescues Faraday::TimeoutError and responds with 504 Gateway Timeout' do
      allow(mock_service).to receive(:search)
        .and_raise(Faraday::TimeoutError.new('Request timed out'))

      get '/youtube/search', params: { q: 'slow_query' }

      expect(response).to have_http_status(:gateway_timeout)
      json = JSON.parse(response.body)
      expect(json['error']).to include('timed out')
    end
  end
end
