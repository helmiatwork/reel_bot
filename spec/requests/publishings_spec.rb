# frozen_string_literal: true

require 'rails_helper'

RSpec.describe 'Publishings', :regression, type: :request do
  let(:project) { create(:video_project, title: 'Viral Video') }
  let(:run) { create(:pipeline_run, video_project: project, run_id: 'run-pub-1', final_video_path: '/tmp/final.mp4') }

  describe 'POST /publish' do
    context 'with pipeline_run_id' do
      before do
        allow(PublishVideoJob).to receive(:perform_later)
      end

      it 'enqueues PublishVideoJob and returns status ok' do
        expect(PublishVideoJob).to receive(:perform_later).with(
          run.id,
          platforms: [ 'youtube', 'tiktok' ]
        )

        post '/publish',
             params: { pipeline_run_id: run.id, platforms: [ 'youtube', 'tiktok' ] }.to_json,
             headers: { 'Content-Type' => 'application/json' }

        expect(response).to have_http_status(:ok)
        json = JSON.parse(response.body)
        expect(json['status']).to eq('ok')
        expect(json['results']).to be_present
      end

      it 'finds by run_id string and enqueues PublishVideoJob' do
        expect(PublishVideoJob).to receive(:perform_later).with(
          run.id,
          platforms: [ 'youtube' ]
        )

        post '/publish',
             params: { pipeline_run_id: 'run-pub-1' }.to_json,
             headers: { 'Content-Type' => 'application/json' }

        expect(response).to have_http_status(:ok)
        json = JSON.parse(response.body)
        expect(json['status']).to eq('ok')
      end

      it 'returns 404 when pipeline_run_id does not exist' do
        post '/publish',
             params: { pipeline_run_id: 'non-existent' }.to_json,
             headers: { 'Content-Type' => 'application/json' }

        expect(response).to have_http_status(:not_found)
        json = JSON.parse(response.body)
        expect(json['error']).to eq('Pipeline run not found')
      end
    end

    context 'with video_path and platforms' do
      let(:multi_publisher) { instance_double(Publishers::MultiPublisher) }

      before do
        allow(Publishers::MultiPublisher).to receive(:new).and_return(multi_publisher)
      end

      it 'calls Publishers::MultiPublisher.new.publish_all and returns status ok' do
        expected_results = {
          'youtube' => { 'video_id' => 'yt_123', 'status' => 'published' }
        }

        expect(multi_publisher).to receive(:publish_all).with(
          video_path: '/tmp/test.mp4',
          script: hash_including('title' => 'Test Video'),
          platforms: [ 'youtube' ],
          credentials: {}
        ).and_return(expected_results)

        post '/publish',
             params: {
               video_path: '/tmp/test.mp4',
               platforms: [ 'youtube' ],
               script: { title: 'Test Video' }
             }.to_json,
             headers: { 'Content-Type' => 'application/json' }

        expect(response).to have_http_status(:ok)
        json = JSON.parse(response.body)
        expect(json['status']).to eq('ok')
        expect(json['results']).to eq(expected_results)
      end

      it 'permits valid credentials parameters and strips unpermitted attributes' do
        expect(multi_publisher).to receive(:publish_all).with(
          video_path: '/tmp/test.mp4',
          script: hash_including('title' => 'Test Video'),
          platforms: [ 'youtube' ],
          credentials: {
            'youtube_token' => 'yt-tok-123',
            'tiktok_token' => 'tt-tok-456'
          }
        ).and_return({ 'youtube' => { 'status' => 'published' } })

        post '/publish',
             params: {
               video_path: '/tmp/test.mp4',
               platforms: [ 'youtube' ],
               script: { title: 'Test Video' },
               credentials: {
                 youtube_token: 'yt-tok-123',
                 tiktok_token: 'tt-tok-456',
                 unauthorized_access_key: 'hacked'
               }
             }.to_json,
             headers: { 'Content-Type' => 'application/json' }

        expect(response).to have_http_status(:ok)
      end
    end

    context 'with invalid or missing parameters' do
      it 'returns 422 if neither pipeline_run_id nor video_path is provided' do
        post '/publish',
             params: { platforms: [ 'youtube' ] }.to_json,
             headers: { 'Content-Type' => 'application/json' }

        expect(response).to have_http_status(:unprocessable_content)
        json = JSON.parse(response.body)
        expect(json['error']).to be_present
      end
    end
  end
end
