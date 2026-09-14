require 'rails_helper'

RSpec.describe FetchAnalyticsJob, type: :job do
  let(:project) { create(:video_project) }
  let(:channel) { create(:channel_account, platform: 'youtube', credentials: { 'access_token' => 'yt_tok' }) }
  let!(:completed_run) do
    create(:pipeline_run,
           video_project: project,
           status: :completed,
           metadata: {
             'publish_results' => {
               'youtube' => { 'id' => 'yt_vid_123', 'platform' => 'youtube' }
             }
           })
  end
  let!(:pending_run) do
    create(:pipeline_run,
           video_project: project,
           status: :pending)
  end

  let(:analytics_service) { instance_double(AnalyticsFetcherService) }
  let(:sample_stats) do
    {
      views: 1200,
      likes: 90,
      comments: 10,
      watch_time_minutes: 300.0,
      ctr: 4.5
    }
  end

  before do
    allow(AnalyticsFetcherService).to receive(:new).and_return(analytics_service)
    allow(analytics_service).to receive(:fetch_youtube_analytics).and_return(sample_stats)
    allow(analytics_service).to receive(:record_snapshot)
  end

  describe '#perform' do
    it 'iterates over completed runs with youtube publish results and records snapshots' do
      expect(analytics_service).to receive(:fetch_youtube_analytics).with('yt_vid_123', credentials: { 'access_token' => 'yt_tok' })
      expect(analytics_service).to receive(:record_snapshot).with(completed_run, channel, sample_stats)

      described_class.new.perform
    end

    it 'ignores runs without youtube publish results' do
      completed_run.update!(metadata: {})

      expect(analytics_service).not_to receive(:fetch_youtube_analytics)
      expect(analytics_service).not_to receive(:record_snapshot)

      described_class.new.perform
    end

    it 'rescues individual fetch errors and continues processing remaining runs' do
      second_run = create(:pipeline_run,
                          video_project: project,
                          status: :completed,
                          metadata: {
                            'publish_results' => {
                              'youtube' => { 'id' => 'yt_vid_456', 'platform' => 'youtube' }
                            }
                          })

      allow(analytics_service).to receive(:fetch_youtube_analytics).with('yt_vid_123', anything).and_raise(StandardError.new('API quota reached'))
      expect(analytics_service).to receive(:fetch_youtube_analytics).with('yt_vid_456', anything).and_return(sample_stats)
      expect(analytics_service).to receive(:record_snapshot).with(second_run, channel, sample_stats)

      expect {
        described_class.new.perform
      }.not_to raise_error
    end
  end
end
