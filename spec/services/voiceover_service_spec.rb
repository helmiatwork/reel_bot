require 'rails_helper'

RSpec.describe VoiceoverService do
  let(:service) { described_class.new(api_key: api_key) }
  let(:api_key) { 'mock-elevenlabs-key' }
  let(:output_path) { Rails.root.join('tmp', 'test_audio.mp3').to_s }
  let(:raw_video_path) { Rails.root.join('tmp', 'test_video.mp4').to_s }
  let(:output_video_path) { Rails.root.join('tmp', 'merged_video.mp4').to_s }

  after do
    FileUtils.rm_f(output_path)
    FileUtils.rm_f(raw_video_path)
    FileUtils.rm_f(output_video_path)
  end

  describe '#text_to_speech' do
    context 'when ElevenLabs API key is provided' do
      it 'calls ElevenLabs API and writes MP3 file' do
        mp3_bytes = 'ELEVENLABS_BINARY_AUDIO'

        stub_request = Faraday.new do |builder|
          builder.adapter :test do |stub|
            stub.post('/v1/text-to-speech/pNInz6obpgDQGcFmaJgB') do |env|
              expect(env.request_headers['xi-api-key']).to eq(api_key)
              payload = JSON.parse(env.body)
              expect(payload['text']).to eq('Hello world!')
              [ 200, { 'content-type' => 'audio/mpeg' }, mp3_bytes ]
            end
          end
        end

        allow(service).to receive(:elevenlabs_connection).and_return(stub_request)

        result = service.text_to_speech('Hello world!', output_path, voice: 'male_neutral')
        expect(result).to eq(output_path)
        expect(File.exist?(output_path)).to be true
        expect(File.read(output_path)).to eq(mp3_bytes)
      end
    end

    context 'when ElevenLabs returns error and fallback succeeds' do
      it 'falls back to local synth / gTTS' do
        stub_request = Faraday.new do |builder|
          builder.adapter :test do |stub|
            stub.post('/v1/text-to-speech/pNInz6obpgDQGcFmaJgB') do |_env|
              [ 429, {}, 'Quota exceeded' ]
            end
          end
        end

        allow(service).to receive(:elevenlabs_connection).and_return(stub_request)
        expect(service).to receive(:fallback_tts).with('Hello fallback', output_path).and_return(output_path)

        result = service.text_to_speech('Hello fallback', output_path)
        expect(result).to eq(output_path)
      end
    end

    context 'when no ElevenLabs API key is present' do
      let(:api_key) { nil }

      it 'directly calls fallback_tts' do
        stub_const('ENV', ENV.to_hash.except('ELEVENLABS_API_KEY'))
        expect(service).to receive(:fallback_tts).with('No key text', output_path).and_return(output_path)

        result = service.text_to_speech('No key text', output_path)
        expect(result).to eq(output_path)
      end
    end
  end

  describe '#merge_with_video' do
    let(:audio_path) { output_path }

    before do
      FileUtils.touch(raw_video_path)
      FileUtils.touch(audio_path)
    end

    it 'executes ffmpeg with array arguments without background music' do
      expected_cmd = [
        'ffmpeg', '-y',
        '-i', raw_video_path,
        '-i', audio_path,
        '-map', '0:v', '-map', '1:a',
        '-c:v', 'copy', '-c:a', 'aac', '-shortest',
        output_video_path
      ]

      status = instance_double(Process::Status, success?: true)
      expect(Open3).to receive(:capture3).with(*expected_cmd).and_return([ '', '', status ])

      result = service.merge_with_video(raw_video_path, audio_path, output_video_path)
      expect(result).to eq(output_video_path)
    end

    it 'mixes background music when provided and file exists' do
      bg_music = Rails.root.join('tmp', 'bg.mp3').to_s
      FileUtils.touch(bg_music)

      expected_cmd = [
        'ffmpeg', '-y',
        '-i', raw_video_path,
        '-i', audio_path,
        '-i', bg_music,
        '-filter_complex', '[1:a]volume=1.0[v];[2:a]volume=0.12[m];[v][m]amix=inputs=2:duration=first[a]',
        '-map', '0:v', '-map', '[a]',
        '-c:v', 'copy', '-c:a', 'aac', '-shortest',
        output_video_path
      ]

      status = instance_double(Process::Status, success?: true)
      expect(Open3).to receive(:capture3).with(*expected_cmd).and_return([ '', '', status ])

      result = service.merge_with_video(raw_video_path, audio_path, output_video_path, bg_music_path: bg_music)
      expect(result).to eq(output_video_path)

      FileUtils.rm_f(bg_music)
    end

    it 'raises VoiceoverService::Error when ffmpeg fails' do
      status = instance_double(Process::Status, success?: false, exitstatus: 1)
      allow(Open3).to receive(:capture3).and_return([ '', 'ffmpeg error: corrupt input', status ])

      expect {
        service.merge_with_video(raw_video_path, audio_path, output_video_path)
      }.to raise_error(VoiceoverService::Error, /FFmpeg failed/)
    end

    it 'raises ArgumentError if raw_video_path does not exist' do
      expect {
        service.merge_with_video('/nonexistent.mp4', audio_path, output_video_path)
      }.to raise_error(ArgumentError, /Raw video not found/)
    end

    it 'raises ArgumentError if audio_path does not exist' do
      expect {
        service.merge_with_video(raw_video_path, '/nonexistent.mp3', output_video_path)
      }.to raise_error(ArgumentError, /Audio not found/)
    end
  end

  describe '#fallback_tts' do
    it 'uses gtts-cli when available' do
      status = instance_double(Process::Status, success?: true)
      expect(Open3).to receive(:capture3)
        .with('gtts-cli', 'Testing gTTS', '--output', output_path) do
          FileUtils.touch(output_path)
          [ '', '', status ]
        end

      result = service.fallback_tts('Testing gTTS', output_path)
      expect(result).to eq(output_path)
    end

    it 'falls back to say command when gtts-cli is not available' do
      gtts_status = instance_double(Process::Status, success?: false)
      say_status = instance_double(Process::Status, success?: true)
      ffmpeg_status = instance_double(Process::Status, success?: true)

      aiff_path = output_path.sub(/\.mp3$/, '.aiff')

      expect(Open3).to receive(:capture3)
        .with('gtts-cli', 'Testing say', '--output', output_path)
        .and_return([ '', '', gtts_status ])

      expect(Open3).to receive(:capture3)
        .with('say', '-o', aiff_path, 'Testing say') do
          FileUtils.touch(aiff_path)
          [ '', '', say_status ]
        end

      expect(Open3).to receive(:capture3)
        .with('ffmpeg', '-y', '-i', aiff_path, output_path) do
          FileUtils.touch(output_path)
          [ '', '', ffmpeg_status ]
        end

      result = service.fallback_tts('Testing say', output_path)
      expect(result).to eq(output_path)
    end

    it 'writes a binary stub if neither gTTS nor say is available' do
      gtts_status = instance_double(Process::Status, success?: false)
      say_status = instance_double(Process::Status, success?: false)

      allow(Open3).to receive(:capture3)
        .with('gtts-cli', anything, '--output', anything)
        .and_return([ '', '', gtts_status ])

      allow(Open3).to receive(:capture3)
        .with('say', '-o', anything, anything)
        .and_return([ '', '', say_status ])

      result = service.fallback_tts('Fallback stub', output_path)
      expect(result).to eq(output_path)
      expect(File.exist?(output_path)).to be true
      expect(File.size(output_path)).to be > 0
    end
  end

  describe '#elevenlabs_connection' do
    it 'creates a Faraday connection to ElevenLabs URL' do
      conn = service.elevenlabs_connection
      expect(conn).to be_a(Faraday::Connection)
      expect(conn.url_prefix.to_s).to start_with('https://api.elevenlabs.io')
    end
  end
end
