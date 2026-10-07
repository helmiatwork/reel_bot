# frozen_string_literal: true

require 'rails_helper'

RSpec.describe 'Voiceovers', :regression, type: :request do
  let(:voiceover_service) { instance_double(VoiceoverService) }

  before do
    allow(VoiceoverService).to receive(:new).and_return(voiceover_service)
  end

  describe 'POST /voiceover/generate' do
    it 'generates TTS audio from script hash and returns audio path' do
      expect(voiceover_service).to receive(:text_to_speech).with(
        'Welcome to this reel',
        any_args
      ).and_return('/tmp/test_audio.mp3')

      post '/voiceover/generate',
           params: { script: { voiceover: 'Welcome to this reel' }, voice: 'male_neutral' }.to_json,
           headers: { 'Content-Type' => 'application/json' }

      expect(response).to have_http_status(:ok)
      json = JSON.parse(response.body)
      expect(json['status']).to eq('ok')
      expect(json['audio_path']).to eq('/tmp/test_audio.mp3')
    end

    it 'generates TTS audio when script is a raw string' do
      expect(voiceover_service).to receive(:text_to_speech).with(
        'Direct speech string',
        any_args
      ).and_return('/tmp/direct_speech.mp3')

      post '/voiceover/generate',
           params: { script: 'Direct speech string' }.to_json,
           headers: { 'Content-Type' => 'application/json' }

      expect(response).to have_http_status(:ok)
      json = JSON.parse(response.body)
      expect(json['status']).to eq('ok')
      expect(json['audio_path']).to eq('/tmp/direct_speech.mp3')
    end

    it 'returns 422 if script is blank' do
      post '/voiceover/generate',
           params: { voice: 'male_neutral' }.to_json,
           headers: { 'Content-Type' => 'application/json' }

      expect(response).to have_http_status(:unprocessable_content)
      json = JSON.parse(response.body)
      expect(json['error']).to be_present
    end
  end

  describe 'POST /voiceover/merge' do
    it 'merges audio with video and returns video path' do
      expect(voiceover_service).to receive(:merge_with_video).with(
        '/tmp/raw.mp4',
        '/tmp/audio.mp3',
        '/tmp/output.mp4',
        bg_music_path: '/tmp/music.mp3'
      ).and_return('/tmp/output.mp4')

      post '/voiceover/merge',
           params: {
             video_path: '/tmp/raw.mp4',
             audio_path: '/tmp/audio.mp3',
             output_path: '/tmp/output.mp4',
             bg_music: '/tmp/music.mp3'
           }.to_json,
           headers: { 'Content-Type' => 'application/json' }

      expect(response).to have_http_status(:ok)
      json = JSON.parse(response.body)
      expect(json['status']).to eq('ok')
      expect(json['video_path']).to eq('/tmp/output.mp4')
    end

    it 'returns 422 if required paths are missing' do
      post '/voiceover/merge',
           params: { video_path: '/tmp/raw.mp4' }.to_json,
           headers: { 'Content-Type' => 'application/json' }

      expect(response).to have_http_status(:unprocessable_content)
      json = JSON.parse(response.body)
      expect(json['error']).to be_present
    end
  end
end
