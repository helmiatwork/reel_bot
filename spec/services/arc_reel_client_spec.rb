require 'rails_helper'

RSpec.describe ArcReelClient do
  let(:base_url) { 'http://arcreel.test:1241' }
  let(:token) { 'test-token-123' }
  let(:client) { described_class.new(url: base_url, token: token) }
  let(:project_id) { 'proj_abc123' }
  let(:dest_path) { Rails.root.join('tmp', 'test_downloads', 'video.mp4').to_s }

  after do
    FileUtils.rm_rf(File.dirname(dest_path))
  end

  describe '#initialize' do
    it 'accepts custom url and token' do
      expect(client.url).to eq(base_url)
      expect(client.token).to eq(token)
    end

    it 'falls back to environment variables or defaults' do
      stub_const('ENV', ENV.to_hash.merge('ARCREEL_URL' => 'http://env-arcreel:1241', 'ARCREEL_TOKEN' => 'env-token'))
      env_client = described_class.new
      expect(env_client.url).to eq('http://env-arcreel:1241')
      expect(env_client.token).to eq('env-token')
    end
  end

  describe '#download_video' do
    context 'when ArcReel returns direct video content' do
      it 'writes video bytes to destination and returns path' do
        video_data = "FAKE_MP4_BINARY_DATA"

        conn = Faraday.new do |builder|
          builder.adapter :test do |stub|
            stub.get("/api/projects/#{project_id}/export") do |env|
              expect(env.request_headers['Authorization']).to eq("Bearer #{token}")
              [ 200, { 'content-type' => 'video/mp4' }, video_data ]
            end
          end
        end

        allow(client).to receive(:connection).and_return(conn)

        result = client.download_video(project_id, dest_path)
        expect(result).to eq(dest_path)
        expect(File.exist?(dest_path)).to be true
        expect(File.read(dest_path)).to eq(video_data)
      end

      it 'streams IO-like response body to disk via IO.copy_stream' do
        video_stream = StringIO.new("STREAMED_VIDEO_CHUNKS")

        response = instance_double(Faraday::Response, status: 200, headers: { 'content-type' => 'video/mp4' }, body: video_stream)
        conn = instance_double(Faraday::Connection)
        allow(conn).to receive(:get).with("/api/projects/#{project_id}/export", nil, anything).and_return(response)
        allow(client).to receive(:connection).and_return(conn)

        expect(IO).to receive(:copy_stream).with(video_stream, instance_of(File)).and_call_original

        result = client.download_video(project_id, dest_path)
        expect(result).to eq(dest_path)
        expect(File.read(dest_path)).to eq("STREAMED_VIDEO_CHUNKS")
      end
    end

    context 'when ArcReel returns JSON with video_url' do
      it 'follows video_url, downloads content, and returns destination' do
        video_url = 'http://cdn.test/rendered_video.mp4'
        video_data = "DOWNLOADED_MP4_CONTENT"

        main_conn = Faraday.new do |builder|
          builder.adapter :test do |stub|
            stub.get("/api/projects/#{project_id}/export") do |_env|
              [ 200, { 'content-type' => 'application/json' }, JSON.dump({ video_url: video_url }) ]
            end
          end
        end

        cdn_conn = Faraday.new do |builder|
          builder.adapter :test do |stub|
            stub.get('/rendered_video.mp4') do |_env|
              [ 200, { 'content-type' => 'video/mp4' }, video_data ]
            end
          end
        end

        allow(client).to receive(:connection).and_return(main_conn)
        allow(Faraday).to receive(:new).with(url: nil).and_return(cdn_conn)
        allow(cdn_conn).to receive(:get).with(video_url) do |&block|
          req = double('Request', options: double('Options'))
          allow(req.options).to receive(:on_data=) do |proc|
            proc.call(video_data, video_data.bytesize)
          end
          block&.call(req)
          double('Response', status: 200, body: '')
        end

        result = client.download_video(project_id, dest_path)
        expect(result).to eq(dest_path)
        expect(File.read(dest_path)).to eq(video_data)
      end

      it 'falls back to writing response body if on_data did not populate file' do
        video_url = 'http://cdn.test/rendered_video.mp4'
        video_data = "DOWNLOADED_MP4_CONTENT"

        main_conn = Faraday.new do |builder|
          builder.adapter :test do |stub|
            stub.get("/api/projects/#{project_id}/export") do |_env|
              [ 200, { 'content-type' => 'application/json' }, JSON.dump({ video_url: video_url }) ]
            end
          end
        end

        cdn_conn = Faraday.new do |builder|
          builder.adapter :test do |stub|
            stub.get('/rendered_video.mp4') do |_env|
              [ 200, { 'content-type' => 'video/mp4' }, video_data ]
            end
          end
        end

        allow(client).to receive(:connection).and_return(main_conn)
        allow(Faraday).to receive(:new).with(url: nil).and_return(cdn_conn)
        allow(cdn_conn).to receive(:get).with(video_url).and_return(
          double('Response', status: 200, body: video_data)
        )

        result = client.download_video(project_id, dest_path)
        expect(result).to eq(dest_path)
        expect(File.read(dest_path)).to eq(video_data)
      end
    end

    context 'when export request fails with non-200 status' do
      it 'raises ArcReelClient::Error' do
        conn = Faraday.new do |builder|
          builder.adapter :test do |stub|
            stub.get("/api/projects/#{project_id}/export") do |_env|
              [ 404, { 'content-type' => 'application/json' }, '{"error": "Project not found"}' ]
            end
          end
        end

        allow(client).to receive(:connection).and_return(conn)

        expect {
          client.download_video(project_id, dest_path)
        }.to raise_error(ArcReelClient::Error, /failed: 404/)
      end
    end

    context 'when JSON response does not have a video URL' do
      it 'raises ArcReelClient::Error' do
        conn = Faraday.new do |builder|
          builder.adapter :test do |stub|
            stub.get("/api/projects/#{project_id}/export") do |_env|
              [ 200, { 'content-type' => 'application/json' }, '{"status": "still_rendering"}' ]
            end
          end
        end

        allow(client).to receive(:connection).and_return(conn)

        expect {
          client.download_video(project_id, dest_path)
        }.to raise_error(ArcReelClient::Error, /missing video_url/)
      end
    end

    context 'when CDN download returns error' do
      it 'raises ArcReelClient::Error' do
        video_url = 'http://cdn.test/bad_video.mp4'
        main_conn = Faraday.new do |builder|
          builder.adapter :test do |stub|
            stub.get("/api/projects/#{project_id}/export") do |_env|
              [ 200, { 'content-type' => 'application/json' }, JSON.dump({ video_url: video_url }) ]
            end
          end
        end

        cdn_conn = Faraday.new do |builder|
          builder.adapter :test do |stub|
            stub.get(video_url) { [ 500, {}, 'CDN error' ] }
          end
        end

        allow(client).to receive(:connection).and_return(main_conn)
        allow(Faraday).to receive(:new).with(url: nil).and_return(cdn_conn)

        expect {
          client.download_video(project_id, dest_path)
        }.to raise_error(ArcReelClient::Error, /Failed to download video from URL/)
      end
    end

    context 'when response contains invalid JSON' do
      it 'raises ArcReelClient::Error' do
        conn = Faraday.new do |builder|
          builder.adapter :test do |stub|
            stub.get("/api/projects/#{project_id}/export") do |_env|
              [ 200, { 'content-type' => 'application/json' }, '{not-json' ]
            end
          end
        end

        allow(client).to receive(:connection).and_return(conn)

        expect {
          client.download_video(project_id, dest_path)
        }.to raise_error(ArcReelClient::Error, /Invalid JSON from ArcReel/)
      end
    end

    context 'when arguments are missing' do
      it 'raises ArgumentError if project_id is blank' do
        expect { client.download_video('', dest_path) }.to raise_error(ArgumentError)
      end

      it 'raises ArgumentError if destination_path is blank' do
        expect { client.download_video(project_id, '') }.to raise_error(ArgumentError)
      end
    end
  end

  describe '#connection' do
    it 'creates a Faraday connection instance with auth headers' do
      conn = client.connection
      expect(conn).to be_a(Faraday::Connection)
      expect(conn.headers['Authorization']).to eq("Bearer #{token}")
    end
  end
end
