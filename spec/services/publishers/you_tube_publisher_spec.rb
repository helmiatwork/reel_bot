require 'rails_helper'
require 'tempfile'

RSpec.describe Publishers::YouTubePublisher do
  let(:video_file) do
    file = Tempfile.new([ 'test_video', '.mp4' ])
    file.binmode
    file.write('fake video binary content')
    file.rewind
    file
  end

  let(:video_path) { video_file.path }
  let(:access_token) { 'ya29.a0AfH6SMC...' }
  let(:credentials) { { access_token: access_token } }
  let(:service) { described_class.new }

  after do
    video_file.close
    video_file.unlink
  end

  describe '#publish' do
    let(:title) { 'Awesome Shorts Video' }
    let(:description) { 'A video about Rails 8 and Ruby 4.0' }
    let(:tags) { [ 'rails', 'ruby', 'shorts' ] }
    let(:resumable_upload_url) { 'https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&upload_id=xyz123' }
    let(:video_id) { 'yt_vid_abc123' }

    it 'initiates resumable upload and uploads video successfully' do
      stub_conn = Faraday.new do |builder|
        builder.adapter :test do |stub|
          stub.post('/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status') do |env|
            expect(env.request_headers['Authorization']).to eq("Bearer #{access_token}")
            expect(env.request_headers['Content-Type']).to include('application/json')
            expect(env.request_headers['X-Upload-Content-Type']).to eq('video/mp4')

            body = JSON.parse(env.body)
            expect(body.dig('snippet', 'title')).to eq(title)
            expect(body.dig('snippet', 'description')).to eq(description)
            expect(body.dig('snippet', 'tags')).to eq(tags)
            expect(body.dig('status', 'privacyStatus')).to eq('private')

            [ 200, { 'location' => resumable_upload_url }, '' ]
          end

          stub.put('/upload/youtube/v3/videos?uploadType=resumable&upload_id=xyz123') do |env|
            expect(env.request_headers['Authorization']).to eq("Bearer #{access_token}")
            expect(env.request_headers['Content-Type']).to eq('video/mp4')
            expect(env.body).to eq(File.binread(video_path))

            [ 200, { 'content-type' => 'application/json' }, JSON.dump({ 'id' => video_id }) ]
          end
        end
      end

      allow(service).to receive(:connection).and_return(stub_conn)

      result = service.publish(
        video_path: video_path,
        title: title,
        description: description,
        tags: tags,
        privacy: 'private',
        credentials: credentials
      )

      expect(result).to eq({
        'id' => video_id,
        'url' => "https://youtu.be/#{video_id}",
        'platform' => 'youtube'
      })
    end

    it 'falls back to upload_url in response body if location header is missing' do
      stub_conn = Faraday.new do |builder|
        builder.adapter :test do |stub|
          stub.post('/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status') do |_env|
            [ 200, { 'content-type' => 'application/json' }, JSON.dump({ 'upload_url' => resumable_upload_url }) ]
          end

          stub.put('/upload/youtube/v3/videos?uploadType=resumable&upload_id=xyz123') do |_env|
            [ 200, { 'content-type' => 'application/json' }, JSON.dump({ 'id' => video_id }) ]
          end
        end
      end

      allow(service).to receive(:connection).and_return(stub_conn)

      result = service.publish(
        video_path: video_path,
        title: title,
        credentials: credentials
      )

      expect(result['id']).to eq(video_id)
    end

    it 'raises Publishers::Error if upload url cannot be found' do
      stub_conn = Faraday.new do |builder|
        builder.adapter :test do |stub|
          stub.post('/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status') do |_env|
            [ 200, { 'content-type' => 'application/json' }, '{}' ]
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
      }.to raise_error(Publishers::Error, /YouTube did not return upload location header/)
    end

    it 'defaults privacy to private when not specified' do
      stub_conn = Faraday.new do |builder|
        builder.adapter :test do |stub|
          stub.post('/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status') do |env|
            body = JSON.parse(env.body)
            expect(body.dig('status', 'privacyStatus')).to eq('private')
            [ 200, { 'location' => resumable_upload_url }, '' ]
          end

          stub.put('/upload/youtube/v3/videos?uploadType=resumable&upload_id=xyz123') do |_env|
            [ 200, { 'content-type' => 'application/json' }, JSON.dump({ 'id' => video_id }) ]
          end
        end
      end

      allow(service).to receive(:connection).and_return(stub_conn)

      result = service.publish(
        video_path: video_path,
        title: title,
        credentials: credentials
      )

      expect(result['id']).to eq(video_id)
    end

    it 'raises ArgumentError if video file does not exist' do
      expect {
        service.publish(
          video_path: '/non/existent/video.mp4',
          title: title,
          credentials: credentials
        )
      }.to raise_error(ArgumentError, /Video file not found/)
    end

    it 'raises ArgumentError if credentials are missing' do
      expect {
        service.publish(
          video_path: video_path,
          title: title,
          credentials: {}
        )
      }.to raise_error(ArgumentError, /YouTube access token is required/)
    end

    it 'raises Publishers::Error if initiation fails' do
      stub_conn = Faraday.new do |builder|
        builder.adapter :test do |stub|
          stub.post('/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status') do |_env|
            [ 401, { 'content-type' => 'application/json' }, '{"error": {"message": "Invalid credentials"}}' ]
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
      }.to raise_error(Publishers::Error, /YouTube session initiation failed/)
    end

    it 'raises Publishers::Error if upload fails' do
      stub_conn = Faraday.new do |builder|
        builder.adapter :test do |stub|
          stub.post('/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status') do |_env|
            [ 200, { 'location' => resumable_upload_url }, '' ]
          end

          stub.put('/upload/youtube/v3/videos?uploadType=resumable&upload_id=xyz123') do |_env|
            [ 500, { 'content-type' => 'application/json' }, '{"error": "Internal Server Error"}' ]
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
      }.to raise_error(Publishers::Error, /YouTube video upload failed/)
    end

    it 'raises Publishers::Error if response has no video ID' do
      stub_conn = Faraday.new do |builder|
        builder.adapter :test do |stub|
          stub.post('/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status') do |_env|
            [ 200, { 'location' => resumable_upload_url }, '' ]
          end

          stub.put('/upload/youtube/v3/videos?uploadType=resumable&upload_id=xyz123') do |_env|
            [ 200, { 'content-type' => 'application/json' }, '{}' ]
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
      }.to raise_error(Publishers::Error, /YouTube response missing video ID/)
    end
  end

  describe '#connection' do
    it 'creates a Faraday connection to YouTube API' do
      conn = service.connection
      expect(conn).to be_a(Faraday::Connection)
      expect(conn.url_prefix.to_s).to start_with('https://www.googleapis.com')
    end
  end
end
