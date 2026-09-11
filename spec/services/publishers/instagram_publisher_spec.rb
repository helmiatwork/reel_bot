require 'rails_helper'
require 'tempfile'

RSpec.describe Publishers::InstagramPublisher do
  let(:video_file) do
    file = Tempfile.new([ 'test_ig', '.mp4' ])
    file.binmode
    file.write('dummy instagram reel video content')
    file.rewind
    file
  end

  let(:video_path) { video_file.path }
  let(:public_url) { 'https://cdn.example.com/videos/reel_123.mp4' }
  let(:caption) { 'Trending Reel #rails #ruby' }
  let(:access_token) { 'IGQVJ...' }
  let(:ig_user_id) { '178414000111222' }
  let(:credentials) do
    {
      access_token: access_token,
      ig_user_id: ig_user_id
    }
  end
  let(:service) { described_class.new }

  after do
    video_file.close
    video_file.unlink
  end

  describe '#publish' do
    let(:container_id) { 'container_id_999' }
    let(:media_id) { 'media_id_888' }

    it 'creates container and publishes reel successfully' do
      stub_conn = Faraday.new do |builder|
        builder.adapter :test do |stub|
          # Step 1: Create media container
          stub.post("/v19.0/#{ig_user_id}/media") do |env|
            body = JSON.parse(env.body)
            expect(body['media_type']).to eq('REELS')
            expect(body['video_url']).to eq(public_url)
            expect(body['caption']).to eq(caption)
            expect(body['access_token']).to eq(access_token)

            [ 200, { 'content-type' => 'application/json' }, JSON.dump({ 'id' => container_id }) ]
          end

          # Step 2: Publish media
          stub.post("/v19.0/#{ig_user_id}/media_publish") do |env|
            body = JSON.parse(env.body)
            expect(body['creation_id']).to eq(container_id)
            expect(body['access_token']).to eq(access_token)

            [ 200, { 'content-type' => 'application/json' }, JSON.dump({ 'id' => media_id }) ]
          end
        end
      end

      allow(service).to receive(:connection).and_return(stub_conn)

      result = service.publish(
        video_path: video_path,
        caption: caption,
        public_url: public_url,
        credentials: credentials
      )

      expect(result).to eq({
        'id' => media_id,
        'platform' => 'instagram',
        'status' => 'published'
      })
    end

    it 'raises ArgumentError if public_url is missing' do
      expect {
        service.publish(
          video_path: video_path,
          caption: caption,
          public_url: nil,
          credentials: credentials
        )
      }.to raise_error(ArgumentError, /public_url is required/)
    end

    it 'raises ArgumentError if video_path is provided but does not exist' do
      expect {
        service.publish(
          video_path: '/non/existent/video.mp4',
          caption: caption,
          public_url: public_url,
          credentials: credentials
        )
      }.to raise_error(ArgumentError, /Video file not found/)
    end

    it 'raises ArgumentError if credentials are incomplete' do
      expect {
        service.publish(
          video_path: video_path,
          caption: caption,
          public_url: public_url,
          credentials: { access_token: access_token }
        )
      }.to raise_error(ArgumentError, /Instagram access token and ig_user_id are required/)
    end

    it 'raises Publishers::Error if container initialization fails' do
      stub_conn = Faraday.new do |builder|
        builder.adapter :test do |stub|
          stub.post("/v19.0/#{ig_user_id}/media") do |_env|
            [ 400, { 'content-type' => 'application/json' }, JSON.dump({
              'error' => { 'message' => 'Invalid video URL' }
            }) ]
          end
        end
      end

      allow(service).to receive(:connection).and_return(stub_conn)

      expect {
        service.publish(
          video_path: video_path,
          caption: caption,
          public_url: public_url,
          credentials: credentials
        )
      }.to raise_error(Publishers::Error, /Instagram container creation failed/)
    end

    it 'raises Publishers::Error if media publish step fails' do
      stub_conn = Faraday.new do |builder|
        builder.adapter :test do |stub|
          stub.post("/v19.0/#{ig_user_id}/media") do |_env|
            [ 200, { 'content-type' => 'application/json' }, JSON.dump({ 'id' => container_id }) ]
          end

          stub.post("/v19.0/#{ig_user_id}/media_publish") do |_env|
            [ 500, { 'content-type' => 'application/json' }, JSON.dump({
              'error' => { 'message' => 'Media processing timeout' }
            }) ]
          end
        end
      end

      allow(service).to receive(:connection).and_return(stub_conn)

      expect {
        service.publish(
          video_path: video_path,
          caption: caption,
          public_url: public_url,
          credentials: credentials
        )
      }.to raise_error(Publishers::Error, /Instagram media publish failed/)
    end

    it 'raises Publishers::Error if container response is missing ID' do
      stub_conn = Faraday.new do |builder|
        builder.adapter :test do |stub|
          stub.post("/v19.0/#{ig_user_id}/media") do |_env|
            [ 200, { 'content-type' => 'application/json' }, '{}' ]
          end
        end
      end

      allow(service).to receive(:connection).and_return(stub_conn)

      expect {
        service.publish(
          video_path: video_path,
          caption: caption,
          public_url: public_url,
          credentials: credentials
        )
      }.to raise_error(Publishers::Error, /Instagram container creation missing ID/)
    end

    it 'raises Publishers::Error if publish response is missing ID' do
      stub_conn = Faraday.new do |builder|
        builder.adapter :test do |stub|
          stub.post("/v19.0/#{ig_user_id}/media") do |_env|
            [ 200, { 'content-type' => 'application/json' }, JSON.dump({ 'id' => container_id }) ]
          end

          stub.post("/v19.0/#{ig_user_id}/media_publish") do |_env|
            [ 200, { 'content-type' => 'application/json' }, '{}' ]
          end
        end
      end

      allow(service).to receive(:connection).and_return(stub_conn)

      expect {
        service.publish(
          video_path: video_path,
          caption: caption,
          public_url: public_url,
          credentials: credentials
        )
      }.to raise_error(Publishers::Error, /Instagram media publish missing ID/)
    end
  end

  describe '#connection' do
    it 'creates a Faraday connection to Meta Graph API' do
      conn = service.connection
      expect(conn).to be_a(Faraday::Connection)
      expect(conn.url_prefix.to_s).to start_with('https://graph.facebook.com')
    end
  end
end
