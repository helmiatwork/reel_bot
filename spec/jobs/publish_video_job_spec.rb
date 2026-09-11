require 'rails_helper'

RSpec.describe PublishVideoJob, type: :job do
  let(:project) { create(:video_project, title: 'AI Productivity Tips', script: { 'title' => 'AI Productivity Tips', 'description' => 'Tips' }) }
  let(:pipeline_run) do
    create(:pipeline_run,
           video_project: project,
           run_id: 'run-job-123',
           final_video_path: '/data/final/video.mp4',
           status: :pending,
           metadata: { 'public_url' => 'https://cdn.example.com/video.mp4' })
  end

  let(:publish_results) do
    {
      'youtube' => { 'id' => 'yt_123', 'url' => 'https://youtu.be/yt_123', 'platform' => 'youtube' },
      'tiktok' => { 'id' => 'tt_123', 'platform' => 'tiktok', 'status' => 'draft' }
    }
  end

  let(:multi_publisher) { instance_double(Publishers::MultiPublisher) }
  let(:telegram_service) { instance_double(TelegramBotService) }

  before do
    allow(Publishers::MultiPublisher).to receive(:new).and_return(multi_publisher)
    allow(TelegramBotService).to receive(:new).and_return(telegram_service)
    allow(telegram_service).to receive(:notify)
  end

  describe '#perform' do
    it 'publishes video to specified platforms, marks run completed, and notifies Telegram' do
      expect(multi_publisher).to receive(:publish_all).with(
        video_path: '/data/final/video.mp4',
        script: project.script,
        platforms: [ 'youtube', 'tiktok' ],
        credentials: a_kind_of(Hash),
        public_url: 'https://cdn.example.com/video.mp4'
      ).and_return(publish_results)

      expect(telegram_service).to receive(:notify).with(
        include('run-job-123')
      )

      described_class.new.perform(pipeline_run.id, platforms: [ 'youtube', 'tiktok' ])

      pipeline_run.reload
      expect(pipeline_run.status).to eq('completed')
      expect(pipeline_run.metadata['publish_results']).to eq(publish_results)
    end

    it 'accepts run_id string instead of integer id' do
      expect(multi_publisher).to receive(:publish_all).and_return(publish_results)

      described_class.new.perform(pipeline_run.run_id, platforms: [ 'youtube' ])

      pipeline_run.reload
      expect(pipeline_run.status).to eq('completed')
    end

    it 'loads channel account credentials when none are passed' do
      create(:channel_account, platform: 'youtube', credentials: { 'access_token' => 'db_yt_token' })

      expect(multi_publisher).to receive(:publish_all) do |args|
        expect(args[:credentials]['youtube']).to eq({ 'access_token' => 'db_yt_token' })
        publish_results
      end

      described_class.new.perform(pipeline_run.id, platforms: [ 'youtube' ])
    end

    it 'handles telegram notification failure gracefully without failing job' do
      expect(multi_publisher).to receive(:publish_all).and_return(publish_results)
      allow(telegram_service).to receive(:notify).and_raise(TelegramBotService::Error.new('Telegram down'))

      described_class.new.perform(pipeline_run.id, platforms: [ 'youtube' ])

      pipeline_run.reload
      expect(pipeline_run.status).to eq('completed')
    end

    it 'handles errors by marking the pipeline run as failed' do
      allow(multi_publisher).to receive(:publish_all).and_raise(StandardError.new('Publish failed: Network timeout'))

      expect {
        described_class.new.perform(pipeline_run.id, platforms: [ 'youtube' ])
      }.to raise_error(StandardError, /Publish failed/)

      pipeline_run.reload
      expect(pipeline_run.status).to eq('failed')
      expect(pipeline_run.error_message).to include('Publish failed: Network timeout')
    end
  end
end
