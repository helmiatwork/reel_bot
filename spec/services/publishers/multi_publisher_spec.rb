require 'rails_helper'

RSpec.describe Publishers::MultiPublisher do
  let(:service) { described_class.new }
  let(:video_path) { '/data/output/video.mp4' }
  let(:script) do
    {
      'title' => 'Top 5 AI Tools',
      'description' => 'Discover the best AI tools of 2026',
      'caption' => 'The best AI tools you must try! #ai #tech',
      'tags' => [ 'ai', 'tech', '2026' ]
    }
  end
  let(:public_url) { 'https://cdn.example.com/videos/video.mp4' }
  let(:credentials) do
    {
      'youtube' => { 'access_token' => 'yt_token' },
      'tiktok' => { 'access_token' => 'tt_token' },
      'instagram' => { 'access_token' => 'ig_token', 'ig_user_id' => 'ig_123' }
    }
  end

  describe '#publish_all' do
    let(:youtube_result) do
      { 'id' => 'yt_123', 'url' => 'https://youtu.be/yt_123', 'platform' => 'youtube' }
    end
    let(:tiktok_result) do
      { 'id' => 'tt_456', 'platform' => 'tiktok', 'status' => 'draft' }
    end
    let(:instagram_result) do
      { 'id' => 'ig_789', 'platform' => 'instagram', 'status' => 'published' }
    end

    before do
      allow_any_instance_of(Publishers::YouTubePublisher).to receive(:publish).and_return(youtube_result)
      allow_any_instance_of(Publishers::TikTokPublisher).to receive(:publish).and_return(tiktok_result)
      allow_any_instance_of(Publishers::InstagramPublisher).to receive(:publish).and_return(instagram_result)
    end

    it 'publishes to all requested platforms and aggregates results' do
      results = service.publish_all(
        video_path: video_path,
        script: script,
        platforms: [ 'youtube', 'tiktok', 'instagram' ],
        credentials: credentials,
        public_url: public_url
      )

      expect(results).to eq({
        'youtube' => youtube_result,
        'tiktok' => tiktok_result,
        'instagram' => instagram_result
      })
    end

    it 'accepts symbol platforms' do
      results = service.publish_all(
        video_path: video_path,
        script: script,
        platforms: [ :youtube, :tiktok ],
        credentials: credentials
      )

      expect(results).to eq({
        'youtube' => youtube_result,
        'tiktok' => tiktok_result
      })
    end

    it 'passes appropriate parameters to each platform publisher' do
      yt_double = instance_double(Publishers::YouTubePublisher)
      tt_double = instance_double(Publishers::TikTokPublisher)

      expect(Publishers::YouTubePublisher).to receive(:new).and_return(yt_double)
      expect(yt_double).to receive(:publish).with(
        video_path: video_path,
        title: 'Top 5 AI Tools',
        description: 'Discover the best AI tools of 2026',
        tags: [ 'ai', 'tech', '2026' ],
        credentials: { 'access_token' => 'yt_token' }
      ).and_return(youtube_result)

      expect(Publishers::TikTokPublisher).to receive(:new).and_return(tt_double)
      expect(tt_double).to receive(:publish).with(
        video_path: video_path,
        title: 'Top 5 AI Tools',
        credentials: { 'access_token' => 'tt_token' }
      ).and_return(tiktok_result)

      service.publish_all(
        video_path: video_path,
        script: script,
        platforms: [ 'youtube', 'tiktok' ],
        credentials: credentials
      )
    end

    it 'returns empty hash when platforms array is empty' do
      results = service.publish_all(
        video_path: video_path,
        script: script,
        platforms: []
      )
      expect(results).to eq({})
    end

    it 'raises ArgumentError for unsupported platforms' do
      expect {
        service.publish_all(
          video_path: video_path,
          script: script,
          platforms: [ 'myspace' ]
        )
      }.to raise_error(ArgumentError, /Unsupported platform: myspace/)
    end
  end
end
