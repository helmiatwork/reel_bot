require 'rails_helper'

RSpec.describe 'Dashboard', type: :request do
  let(:project) { create(:video_project, title: 'Viral AI Reels') }
  let!(:run1) do
    create(:pipeline_run,
           video_project: project,
           run_id: 'run-dash-1',
           status: :completed,
           quality_score: 92)
  end
  let!(:run2) do
    create(:pipeline_run,
           video_project: project,
           run_id: 'run-dash-2',
           status: :running,
           quality_score: 75,
           metadata: { 'approval_status' => 'awaiting_approval' })
  end
  let!(:run3) do
    create(:pipeline_run,
           video_project: project,
           run_id: 'run-dash-3',
           status: :failed,
           quality_score: nil,
           metadata: { 'approval_status' => 'approved' })
  end

  let(:channel) { create(:channel_account) }
  let!(:snapshot) { create(:analytics_snapshot, pipeline_run: run1, channel_account: channel, views: 25000) }

  describe 'GET /' do
    it 'renders the dashboard with stats, recent runs, and insights' do
      get '/'

      expect(response).to have_http_status(:ok)
      expect(response.body).to include('ReelBot Dashboard')
      expect(response.body).to include('run-dash-1')
      expect(response.body).to include('run-dash-2')
      expect(response.body).to include('run-dash-3')
      expect(response.body).to include('Viral AI Reels')
      expect(response.body).to include('Approve')
      expect(response.body).to include('Approved')
      expect(response.body).to include('FAILED')
    end

    it 'renders empty message when no runs exist' do
      PipelineRun.destroy_all

      get '/'

      expect(response).to have_http_status(:ok)
      expect(response.body).to include('No pipeline runs recorded yet')
    end

    it 'caches AI insights to avoid calling LLM synchronously on every page load' do
      expect(Rails.cache).to receive(:fetch).with('dashboard_ai_insights', expires_in: 1.hour).and_call_original

      get '/'
      expect(response).to have_http_status(:ok)
    end
  end

  describe 'POST /pipeline_runs/:id/approve' do
    before do
      allow(PublishVideoJob).to receive(:perform_later)
    end

    it 'approves the run, enqueues PublishVideoJob, and redirects with flash notice' do
      expect(PublishVideoJob).to receive(:perform_later).with(run2.id)

      post "/pipeline_runs/#{run2.id}/approve"

      expect(response).to redirect_to('/')
      follow_redirect!
      expect(response.body).to include('approved for publishing')

      run2.reload
      expect(run2.metadata['approval_status']).to eq('approved')
    end

    it 'handles turbo_stream request format' do
      expect(PublishVideoJob).to receive(:perform_later).with(run2.id)

      post "/pipeline_runs/#{run2.id}/approve", headers: { 'Accept' => 'text/vnd.turbo-stream.html' }

      expect(response).to have_http_status(:ok)
      expect(response.media_type).to eq('text/vnd.turbo-stream.html')
      expect(response.body).to include('turbo-stream action="replace"')
      expect(response.body).to include('turbo-stream action="update"')
    end
  end
end
