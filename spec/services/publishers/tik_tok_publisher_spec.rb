require 'rails_helper'
require 'tempfile'

RSpec.describe Publishers::TikTokPublisher do
  let(:video_file) do
    file = Tempfile.new([ 'test_tiktok', '.mp4' ])
    file.binmode
    file.write('dummy tiktok video content')
    file.rewind
    file
  end

  let(:video_path) { video_file.path }
  let(:access_token) { 'act.tiktok_access_token_123' }
  let(:credentials) { { access_token: access_token } }
  let(:service) { described_class.new }

  after do
    video_file.close
    video_file.unlink
  end

  describe '#publish' do
    let(:title) { 'Viral Reel on TikTok' }
    let(:publish_id) { 'v_pub_file_98765' }
    let(:upload_url) { 'https://open-upload.tiktokapis.com/video/upload/chunk123' }

    it 'initializes video posting and uploads chunks successfully' do
      stub_conn = Faraday.new do |builder|
        builder.adapter :test do |stub|
          # Step 1: Init video upload
          stub.post('/v2/post/publish/video/init/') do |env|
            expect(env.request_headers['Authorization']).to eq("Bearer #{access_token}")
            expect(env.request_headers['Content-Type']).to include('application/json')

            body = JSON.parse(env.body)
            expect(body.dig('post_info', 'title')).to eq(title)
            expect(body.dig('source_info', 'source')).to eq('FILE_UPLOAD')
            expect(body.dig('source_info', 'video_size')).to eq(File.size(video_path))

            [ 200, { 'content-type' => 'application/json' }, JSON.dump({
              'data' => {
                'publish_id' => publish_id,
                'upload_url' => upload_url
              },
              'error' => { 'code' => 'ok', 'message' => '' }
            }) ]
          end

          # Step 2: Upload binary
          stub.put('/video/upload/chunk123') do |env|
            expect(env.request_headers['Content-Type']).to eq('video/mp4')
            expect(env.request_headers['Content-Range']).to eq("bytes 0-#{File.size(video_path) - 1}/#{File.size(video_path)}")
            expect(env.body).to eq(File.binread(video_path))

            [ 200, { 'content-type' => 'application/json' }, '' ]
          end
        end
      end

      allow(service).to receive(:connection).and_return(stub_conn)

      result = service.publish(
        video_path: video_path,
        title: title,
        credentials: credentials
      )

      expect(result).to eq({
        'id' => publish_id,
        'platform' => 'tiktok',
        'status' => 'draft'
      })
    end

    it 'raises ArgumentError if video file is not found' do
      expect {
        service.publish(
          video_path: '/missing/video.mp4',
          title: title,
          credentials: credentials
        )
      }.to raise_error(ArgumentError, /Video file not found/)
    end

    it 'raises ArgumentError if access token is missing' do
      expect {
        service.publish(
          video_path: video_path,
          title: title,
          credentials: {}
        )
      }.to raise_error(ArgumentError, /TikTok access token is required/)
    end

    it 'raises Publishers::Error if TikTok init API fails' do
      stub_conn = Faraday.new do |builder|
        builder.adapter :test do |stub|
          stub.post('/v2/post/publish/video/init/') do |_env|
            [ 400, { 'content-type' => 'application/json' }, JSON.dump({
              'error' => { 'code' => 'invalid_param', 'message' => 'Invalid title length' }
            }) ]
          end
        end
      end

      allow(service).to receive(:connection).and_return(stub_conn)

      expect {
        service.publish(
          video_path: video_path,
          title: title,
          credentials: credentials
        )
      }.to raise_error(Publishers::Error, /TikTok video init failed/)
    end

    it 'raises Publishers::Error if TikTok returns error in 200 response' do
      stub_conn = Faraday.new do |builder|
        builder.adapter :test do |stub|
          stub.post('/v2/post/publish/video/init/') do |_env|
            [ 200, { 'content-type' => 'application/json' }, JSON.dump({
              'error' => { 'code' => 'spam_risk_user_banned', 'message' => 'User banned' }
            }) ]
          end
        end
      end

      allow(service).to receive(:connection).and_return(stub_conn)

      expect {
        service.publish(
          video_path: video_path,
          title: title,
          credentials: credentials
        )
      }.to raise_error(Publishers::Error, /User banned/)
    end

    it 'raises Publishers::Error if video binary upload fails' do
      stub_conn = Faraday.new do |builder|
        builder.adapter :test do |stub|
          stub.post('/v2/post/publish/video/init/') do |_env|
            [ 200, { 'content-type' => 'application/json' }, JSON.dump({
              'data' => {
                'publish_id' => publish_id,
                'upload_url' => upload_url
              },
              'error' => { 'code' => 'ok' }
            }) ]
          end

          stub.put('/video/upload/chunk123') do |_env|
            [ 502, { 'content-type' => 'application/json' }, 'Bad Gateway' ]
          end
        end
      end

      allow(service).to receive(:connection).and_return(stub_conn)

      expect {
        service.publish(
          video_path: video_path,
          title: title,
          credentials: credentials
        )
      }.to raise_error(Publishers::Error, /TikTok video upload failed/)
    end
  end

  describe '#connection' do
    it 'creates a Faraday connection to TikTok API' do
      conn = service.connection
      expect(conn).to be_a(Faraday::Connection)
      expect(conn.url_prefix.to_s).to start_with('https://open.tiktokapis.com')
    end
  end
end
