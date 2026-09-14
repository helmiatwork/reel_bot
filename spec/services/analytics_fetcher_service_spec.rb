require 'rails_helper'

RSpec.describe AnalyticsFetcherService do
  let(:service) { described_class.new }
  let(:access_token) { 'yt_access_token_123' }
  let(:credentials) { { access_token: access_token } }
  let(:video_id) { 'dQw4w9WgXcQ' }

  describe '#fetch_youtube_analytics' do
    it 'fetches video statistics and analytics metrics via Faraday' do
      data_conn = Faraday.new do |builder|
        builder.adapter :test do |stub|
          stub.get("/youtube/v3/videos?id=#{video_id}&part=statistics") do |env|
            expect(env.request_headers['Authorization']).to eq("Bearer #{access_token}")
            [ 200, { 'content-type' => 'application/json' }, JSON.dump({
              'items' => [
                {
                  'statistics' => {
                    'viewCount' => '15200',
                    'likeCount' => '1250',
                    'commentCount' => '85'
                  }
                }
              ]
            }) ]
          end
        end
      end

      analytics_conn = Faraday.new do |builder|
        builder.adapter :test do |stub|
          stub.get("/v2/reports?endDate=#{Date.current}&filters=video%3D%3D#{video_id}&ids=channel%3D%3DMINE&metrics=estimatedMinutesWatched%2CaverageViewPercentage&startDate=2020-01-01") do |env|
            expect(env.request_headers['Authorization']).to eq("Bearer #{access_token}")
            [ 200, { 'content-type' => 'application/json' }, JSON.dump({
              'rows' => [
                [ 4520.5, 68.5 ]
              ]
            }) ]
          end
        end
      end

      allow(service).to receive(:youtube_data_connection).and_return(data_conn)
      allow(service).to receive(:youtube_analytics_connection).and_return(analytics_conn)

      result = service.fetch_youtube_analytics(video_id, credentials: credentials)

      expect(result).to eq({
        views: 15200,
        likes: 1250,
        comments: 85,
        watch_time_minutes: 4520.5,
        ctr: 68.5
      })
    end

    it 'raises ArgumentError if video_id is blank' do
      expect {
        service.fetch_youtube_analytics('', credentials: credentials)
      }.to raise_error(ArgumentError, /video_id is required/)
    end

    it 'raises ArgumentError if credentials are missing' do
      expect {
        service.fetch_youtube_analytics(video_id, credentials: {})
      }.to raise_error(ArgumentError, /YouTube access token is required/)
    end

    it 'handles missing video items from YouTube API' do
      data_conn = Faraday.new do |builder|
        builder.adapter :test do |stub|
          stub.get("/youtube/v3/videos?id=#{video_id}&part=statistics") do |_env|
            [ 200, { 'content-type' => 'application/json' }, '{"items": []}' ]
          end
        end
      end

      analytics_conn = Faraday.new do |builder|
        builder.adapter :test do |stub|
          stub.get("/v2/reports?endDate=#{Date.current}&filters=video%3D%3D#{video_id}&ids=channel%3D%3DMINE&metrics=estimatedMinutesWatched%2CaverageViewPercentage&startDate=2020-01-01") do |_env|
            [ 200, { 'content-type' => 'application/json' }, '{"rows": []}' ]
          end
        end
      end

      allow(service).to receive(:youtube_data_connection).and_return(data_conn)
      allow(service).to receive(:youtube_analytics_connection).and_return(analytics_conn)

      result = service.fetch_youtube_analytics(video_id, credentials: credentials)

      expect(result).to eq({
        views: 0,
        likes: 0,
        comments: 0,
        watch_time_minutes: 0.0,
        ctr: 0.0
      })
    end
  end

  describe '#record_snapshot' do
    let(:project) { create(:video_project) }
    let(:pipeline_run) { create(:pipeline_run, video_project: project) }
    let(:channel_account) { create(:channel_account, platform: 'youtube') }
    let(:stats) do
      {
        views: 5000,
        watch_time_minutes: 120.5,
        likes: 450,
        comments: 32,
        ctr: 5.4,
        raw_payload: { 'test' => 'data' }
      }
    end

    it 'creates an AnalyticsSnapshot record with valid attributes' do
      expect {
        service.record_snapshot(pipeline_run, channel_account, stats)
      }.to change(AnalyticsSnapshot, :count).by(1)

      snapshot = AnalyticsSnapshot.last
      expect(snapshot.pipeline_run).to eq(pipeline_run)
      expect(snapshot.channel_account).to eq(channel_account)
      expect(snapshot.views).to eq(5000)
      expect(snapshot.watch_time_minutes).to eq(120.5)
      expect(snapshot.likes).to eq(450)
      expect(snapshot.comments).to eq(32)
      expect(snapshot.ctr).to eq(5.4)
    end
  end

  describe '#generate_insights' do
    let(:project_top) { create(:video_project, title: 'Top Performing Video') }
    let(:project_bot) { create(:video_project, title: 'Low Performing Video') }
    let(:channel) { create(:channel_account) }
    let(:run_top) { create(:pipeline_run, video_project: project_top, quality_score: 95) }
    let(:run_bot) { create(:pipeline_run, video_project: project_bot, quality_score: 55) }

    before do
      create(:analytics_snapshot, pipeline_run: run_top, channel_account: channel, views: 50000, likes: 4000)
      create(:analytics_snapshot, pipeline_run: run_bot, channel_account: channel, views: 100, likes: 5)
    end

    it 'queries LLM via Faraday and returns structured suggestions' do
      cliproxy_conn = Faraday.new do |builder|
        builder.adapter :test do |stub|
          stub.post('/v1/chat/completions') do |env|
            body = JSON.parse(env.body)
            expect(body['messages']).to be_present

            llm_response = {
              'choices' => [
                {
                  'message' => {
                    'content' => JSON.dump({
                      'summary' => 'High hook retention and energetic pacing drove 50k views.',
                      'top_patterns' => [ 'Fast visual hook under 2 seconds', 'Clear text subtitles' ],
                      'improvements' => [ 'Avoid slow introductions in lower performing reels' ],
                      'suggested_hooks' => [ 'Here is the secret nobody tells you about AI' ]
                    })
                  }
                }
              ]
            }

            [ 200, { 'content-type' => 'application/json' }, JSON.dump(llm_response) ]
          end
        end
      end

      allow(service).to receive(:cliproxy_connection).and_return(cliproxy_conn)

      insights = service.generate_insights

      expect(insights[:summary]).to include('High hook retention')
      expect(insights[:top_patterns]).to include('Fast visual hook under 2 seconds')
      expect(insights[:improvements]).to include('Avoid slow introductions in lower performing reels')
      expect(insights[:suggested_hooks]).to be_an(Array)
    end

    it 'handles LLM API errors gracefully with fallback insights' do
      cliproxy_conn = Faraday.new do |builder|
        builder.adapter :test do |stub|
          stub.post('/v1/chat/completions') do |_env|
            [ 500, { 'content-type' => 'application/json' }, '{"error": "LLM service unavailable"}' ]
          end
        end
      end

      allow(service).to receive(:cliproxy_connection).and_return(cliproxy_conn)

      insights = service.generate_insights

      expect(insights[:summary]).to be_present
      expect(insights[:top_patterns]).to be_an(Array)
      expect(insights[:improvements]).to be_an(Array)
    end

    it 'handles markdown fenced json in LLM response' do
      cliproxy_conn = Faraday.new do |builder|
        builder.adapter :test do |stub|
          stub.post('/v1/chat/completions') do |_env|
            [ 200, { 'content-type' => 'application/json' }, JSON.dump({
              'choices' => [
                {
                  'message' => {
                    'content' => "```json\n{\"summary\": \"Great job\", \"top_patterns\": [], \"improvements\": [], \"suggested_hooks\": []}\n```"
                  }
                }
              ]
            }) ]
          end
        end
      end

      allow(service).to receive(:cliproxy_connection).and_return(cliproxy_conn)

      insights = service.generate_insights
      expect(insights[:summary]).to eq('Great job')
    end

    it 'falls back to default insights when LLM response is not valid json' do
      cliproxy_conn = Faraday.new do |builder|
        builder.adapter :test do |stub|
          stub.post('/v1/chat/completions') do |_env|
            [ 200, { 'content-type' => 'application/json' }, '{"choices": [{"message": {"content": "not json"}}]}' ]
          end
        end
      end

      allow(service).to receive(:cliproxy_connection).and_return(cliproxy_conn)

      insights = service.generate_insights
      expect(insights[:summary]).to include('Short-form videos')
    end
  end

  describe '#fetch_youtube_analytics edge cases' do
    it 'handles non-200 responses from YouTube Data API' do
      data_conn = Faraday.new do |builder|
        builder.adapter :test do |stub|
          stub.get("/youtube/v3/videos?id=#{video_id}&part=statistics") do |_env|
            [ 403, { 'content-type' => 'application/json' }, '{"error": "quotaExceeded"}' ]
          end
        end
      end

      analytics_conn = Faraday.new do |builder|
        builder.adapter :test do |stub|
          stub.get("/v2/reports?endDate=#{Date.current}&filters=video%3D%3D#{video_id}&ids=channel%3D%3DMINE&metrics=estimatedMinutesWatched%2CaverageViewPercentage&startDate=2020-01-01") do |_env|
            [ 403, { 'content-type' => 'application/json' }, '{"error": "quotaExceeded"}' ]
          end
        end
      end

      allow(service).to receive(:youtube_data_connection).and_return(data_conn)
      allow(service).to receive(:youtube_analytics_connection).and_return(analytics_conn)

      result = service.fetch_youtube_analytics(video_id, credentials: credentials)
      expect(result[:views]).to eq(0)
      expect(result[:watch_time_minutes]).to eq(0.0)
    end
  end

  describe 'default connections' do
    it 'creates Faraday connections' do
      expect(service.youtube_data_connection).to be_a(Faraday::Connection)
      expect(service.youtube_analytics_connection).to be_a(Faraday::Connection)
      expect(service.cliproxy_connection).to be_a(Faraday::Connection)
    end
  end
end
