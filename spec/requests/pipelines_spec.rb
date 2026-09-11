# frozen_string_literal: true

require 'rails_helper'

RSpec.describe 'Pipelines', type: :request do
  let(:project) { create(:video_project, title: 'Viral AI Reel') }
  let!(:run1) { create(:pipeline_run, video_project: project, run_id: 'run-123', status: :completed, quality_score: 88) }
  let!(:run2) { create(:pipeline_run, video_project: project, run_id: 'run-456', status: :pending) }

  describe 'POST /pipeline/run' do
    let(:valid_payload) do
      {
        script: {
          title: 'Top 5 AI Tools',
          hook: 'You will not believe these AI tools',
          voiceover: 'Here are the top 5 AI tools in 2026.',
          topic: 'AI Technology'
        },
        arcreel_project_id: 'arc-proj-999',
        user_id: 'user-42',
        platforms: [ 'youtube', 'tiktok' ],
        voice: 'female_warm',
        auto_publish: false
      }
    end

    before do
      allow(CompletePipelineJob).to receive(:perform_later)
    end

    it 'creates a PipelineRun, enqueues CompletePipelineJob, and responds with 202 Accepted' do
      expect {
        post '/pipeline/run', params: valid_payload.to_json, headers: { 'Content-Type' => 'application/json' }
      }.to change(PipelineRun, :count).by(1)

      expect(response).to have_http_status(:accepted)
      json = JSON.parse(response.body)
      expect(json['status']).to eq('started')
      expect(json['run_id']).to be_present

      created_run = PipelineRun.find_by(run_id: json['run_id'])
      expect(created_run).to be_present
      expect(created_run.status).to eq('pending')
      expect(created_run.metadata['arcreel_project_id']).to eq('arc-proj-999')
      expect(created_run.metadata['user_id']).to eq('user-42')
      expect(created_run.metadata['voice']).to eq('female_warm')

      expect(CompletePipelineJob).to have_received(:perform_later).with(
        created_run.id,
        auto_publish: false,
        platforms: [ 'youtube', 'tiktok' ]
      )
    end

    it 'defaults platforms to ["youtube"] when not provided' do
      payload = {
        script: { title: 'Default Platform Test' },
        arcreel_project_id: 'arc-proj-default'
      }

      post '/pipeline/run', params: payload.to_json, headers: { 'Content-Type' => 'application/json' }

      expect(response).to have_http_status(:accepted)
      json = JSON.parse(response.body)
      created_run = PipelineRun.find_by(run_id: json['run_id'])

      expect(CompletePipelineJob).to have_received(:perform_later).with(
        created_run.id,
        auto_publish: false,
        platforms: [ 'youtube' ]
      )
    end

    it 'returns 422 when arcreel_project_id is missing' do
      post '/pipeline/run', params: { script: { title: 'Test' } }.to_json, headers: { 'Content-Type' => 'application/json' }
      expect(response).to have_http_status(:unprocessable_content)
      json = JSON.parse(response.body)
      expect(json['error']).to include('arcreel_project_id')
    end

    it 'returns 422 when script is missing or empty' do
      post '/pipeline/run', params: { arcreel_project_id: 'arc-123', script: {} }.to_json, headers: { 'Content-Type' => 'application/json' }
      expect(response).to have_http_status(:unprocessable_content)
      json = JSON.parse(response.body)
      expect(json['error']).to include('script')
    end
  end

  describe 'GET /pipeline/runs' do
    it 'returns an array of pipeline runs as JSON' do
      get '/pipeline/runs'

      expect(response).to have_http_status(:ok)
      json = JSON.parse(response.body)
      expect(json).to be_an(Array)
      expect(json.size).to eq(2)
      run_ids = json.map { |r| r['run_id'] }
      expect(run_ids).to include('run-123', 'run-456')
    end
  end

  describe 'GET /pipeline/run/:id' do
    it 'finds pipeline run by numeric id' do
      get "/pipeline/run/#{run1.id}"

      expect(response).to have_http_status(:ok)
      json = JSON.parse(response.body)
      expect(json['id']).to eq(run1.id)
      expect(json['run_id']).to eq('run-123')
      expect(json['status']).to eq('completed')
      expect(json['quality_score']).to eq(88)
    end

    it 'finds pipeline run by string run_id' do
      get "/pipeline/run/#{run1.run_id}"

      expect(response).to have_http_status(:ok)
      json = JSON.parse(response.body)
      expect(json['run_id']).to eq('run-123')
      expect(json['status']).to eq('completed')
    end

    it 'returns 404 when run is not found' do
      get '/pipeline/run/non-existent-id'

      expect(response).to have_http_status(:not_found)
      json = JSON.parse(response.body)
      expect(json['error']).to eq('Pipeline run not found')
    end
  end
end
