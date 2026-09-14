require 'rails_helper'

RSpec.describe QualityCheckService do
  let(:service) { described_class.new(api_url: 'http://cliproxy.test:8317/v1', api_key: 'test-key') }
  let(:video_path) { Rails.root.join('tmp', 'sample_video.mp4').to_s }
  let(:script) { { 'title' => 'Tech Shorts 01', 'topic' => 'AI' } }

  before do
    FileUtils.touch(video_path)
  end

  after do
    FileUtils.rm_f(video_path)
  end

  describe '#extract_sample_frames' do
    it 'calls ffprobe to get duration and ffmpeg to extract evenly spaced frames' do
      probe_status = instance_double(Process::Status, success?: true)
      ffmpeg_status = instance_double(Process::Status, success?: true)

      expect(Open3).to receive(:capture3)
        .with('ffprobe', '-v', 'quiet', '-show_entries', 'format=duration', '-of', 'csv=p=0', video_path)
        .and_return([ "30.0\n", '', probe_status ])

      expect(Open3).to receive(:capture3)
        .with('ffmpeg', '-y', '-ss', anything, '-i', video_path, '-vframes', '1', '-q:v', '3', anything)
        .exactly(5).times do |*args|
          frame_dest = args.last
          FileUtils.touch(frame_dest)
          [ '', '', ffmpeg_status ]
        end

      frames = service.extract_sample_frames(video_path, count: 5)
      expect(frames.size).to eq(5)
      expect(frames.first).to have_key(:path)
      expect(frames.first).to have_key(:timestamp)

      frames.each { |f| FileUtils.rm_f(f[:path]) }
    end
  end

  describe '#evaluate_quality' do
    let(:sample_frame) { Rails.root.join('tmp', 'frame_001.jpg').to_s }

    before do
      File.binwrite(sample_frame, 'FAKE_JPEG_BINARY')
      allow(service).to receive(:extract_sample_frames).and_return([
        { path: sample_frame, timestamp: '00:05' }
      ])
    end

    after do
      FileUtils.rm_f(sample_frame)
    end

    it 'sends base64 frames to vision model and parses structured assessment' do
      ai_response = {
        choices: [
          {
            message: {
              content: <<~JSON
                {
                  "overall_score": 88,
                  "recommendation": "approve",
                  "issues": []
                }
              JSON
            }
          }
        ]
      }

      stub_conn = Faraday.new do |builder|
        builder.adapter :test do |stub|
          stub.post('/v1/chat/completions') do |env|
            expect(env.request_headers['Authorization']).to eq('Bearer test-key')
            body = JSON.parse(env.body)
            expect(body['model']).to eq('gemini-2.5-flash')
            messages = body['messages']
            user_content = messages.find { |m| m['role'] == 'user' }['content']
            image_part = user_content.find { |c| c['type'] == 'image_url' }
            expect(image_part['image_url']['url']).to start_with('data:image/jpeg;base64,')
            [ 200, { 'content-type' => 'application/json' }, JSON.dump(ai_response) ]
          end
        end
      end

      allow(service).to receive(:cliproxy_connection).and_return(stub_conn)

      result = service.evaluate_quality(video_path, script)
      expect(result[:overall_score]).to eq(88)
      expect(result[:recommendation]).to eq('approve')
      expect(result[:issues]).to eq([])
    end

    it 'handles markdown fenced json in model response' do
      ai_response = {
        choices: [
          {
            message: {
              content: "```json\n{\"overall_score\": 45, \"recommendation\": \"reject\", \"issues\": [\"blurry text\"]}\n```"
            }
          }
        ]
      }

      stub_conn = Faraday.new do |builder|
        builder.adapter :test do |stub|
          stub.post('/v1/chat/completions') do |_env|
            [ 200, { 'content-type' => 'application/json' }, JSON.dump(ai_response) ]
          end
        end
      end

      allow(service).to receive(:cliproxy_connection).and_return(stub_conn)

      result = service.evaluate_quality(video_path, script)
      expect(result[:overall_score]).to eq(45)
      expect(result[:recommendation]).to eq('reject')
      expect(result[:issues]).to eq([ 'blurry text' ])
    end

    it 'returns fallback review assessment if API fails' do
      stub_conn = Faraday.new do |builder|
        builder.adapter :test do |stub|
          stub.post('/v1/chat/completions') do |_env|
            [ 500, {}, 'Internal Server Error' ]
          end
        end
      end

      allow(service).to receive(:cliproxy_connection).and_return(stub_conn)

      result = service.evaluate_quality(video_path, script)
      expect(result[:overall_score]).to eq(50)
      expect(result[:recommendation]).to eq('review')
      expect(result[:issues]).to include('quality_check_api_error')
    end

    it 'returns rejection when no frames can be extracted' do
      allow(service).to receive(:extract_sample_frames).and_return([])

      result = service.evaluate_quality(video_path, script)
      expect(result[:overall_score]).to eq(0)
      expect(result[:recommendation]).to eq('reject')
      expect(result[:issues]).to eq([ 'no_frames_extracted' ])
    end

    it 'falls back to score 50 on malformed json body' do
      stub_conn = Faraday.new do |builder|
        builder.adapter :test do |stub|
          stub.post('/v1/chat/completions') do |_env|
            [ 200, { 'content-type' => 'application/json' }, '{"choices": [{"message": {"content": "not valid json"}}]}' ]
          end
        end
      end

      allow(service).to receive(:cliproxy_connection).and_return(stub_conn)

      result = service.evaluate_quality(video_path, script)
      expect(result[:overall_score]).to eq(50)
      expect(result[:recommendation]).to eq('review')
      expect(result[:issues]).to eq([ 'parse_error' ])
    end
  end

  describe '#extract_sample_frames error handling' do
    it 'raises ArgumentError if video file does not exist' do
      expect {
        service.extract_sample_frames('/nonexistent/video.mp4')
      }.to raise_error(ArgumentError, /Video not found/)
    end

    it 'defaults duration to 60.0 if ffprobe fails' do
      probe_status = instance_double(Process::Status, success?: false)
      ffmpeg_status = instance_double(Process::Status, success?: true)

      expect(Open3).to receive(:capture3)
        .with('ffprobe', anything, anything, anything, anything, anything, anything, video_path)
        .and_return([ '', 'ffprobe error', probe_status ])

      expect(Open3).to receive(:capture3)
        .with('ffmpeg', anything, anything, anything, anything, video_path, anything, anything, anything, anything, anything)
        .at_least(:once) do |*args|
          FileUtils.touch(args.last)
          [ '', '', ffmpeg_status ]
        end

      frames = service.extract_sample_frames(video_path, count: 2)
      expect(frames.size).to eq(2)
      frames.each { |f| FileUtils.rm_f(f[:path]) }
    end
  end

  describe '#cliproxy_connection' do
    it 'creates a Faraday connection instance' do
      conn = service.cliproxy_connection
      expect(conn).to be_a(Faraday::Connection)
      expect(conn.url_prefix.to_s).to eq('http://cliproxy.test:8317/v1')
    end
  end
end
