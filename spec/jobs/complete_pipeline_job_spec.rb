require 'rails_helper'

RSpec.describe CompletePipelineJob, type: :job do
  let(:project) do
    create(:video_project,
           title: 'Rails 8 Features',
           hook: 'Watch what is new in Rails 8',
           script: {
             'title' => 'Rails 8 Features',
             'voiceover' => 'Rails 8 is finally here with Solid Queue and Solid Cable.',
             'segments' => [
               { 'start_time' => 0.0, 'end_time' => 2.5, 'text' => 'Rails 8 is finally here' }
             ]
           })
  end

  let(:pipeline_run) do
    create(:pipeline_run,
           video_project: project,
           run_id: 'pipe-run-101',
           status: :pending,
           raw_video_path: nil,
           final_video_path: nil,
           subtitles_path: nil,
           metadata: {})
  end

  let(:arc_reel_client) { instance_double(ArcReelClient) }
  let(:voiceover_service) { instance_double(VoiceoverService) }
  let(:subtitle_service) { instance_double(SubtitleService) }
  let(:qc_service) { instance_double(QualityCheckService) }
  let(:telegram_service) { instance_double(TelegramBotService) }

  before do
    allow(ArcReelClient).to receive(:new).and_return(arc_reel_client)
    allow(VoiceoverService).to receive(:new).and_return(voiceover_service)
    allow(SubtitleService).to receive(:new).and_return(subtitle_service)
    allow(QualityCheckService).to receive(:new).and_return(qc_service)
    allow(TelegramBotService).to receive(:new).and_return(telegram_service)

    allow(arc_reel_client).to receive(:download_video).and_return('/tmp/raw.mp4')
    allow(voiceover_service).to receive(:text_to_speech).and_return('/tmp/voiceover.mp3')
    allow(voiceover_service).to receive(:merge_with_video).and_return('/tmp/merged.mp4')
    allow(subtitle_service).to receive(:generate_srt).and_return('/tmp/subtitles.srt')
    allow(subtitle_service).to receive(:burn_subtitles).and_return('/tmp/final.mp4')
    allow(telegram_service).to receive(:request_approval)
  end

  describe '#perform' do
    context 'when auto_publish is false' do
      before do
        allow(qc_service).to receive(:evaluate_quality).and_return({
          overall_score: 95,
          recommendation: 'approve',
          issues: []
        })
      end

      it 'executes pipeline steps, records completed steps, and requests approval via Telegram' do
        expect(PublishVideoJob).not_to receive(:perform_later)
        expect(telegram_service).to receive(:request_approval).with(instance_of(PipelineRun))

        described_class.new.perform(pipeline_run.id, auto_publish: false)

        pipeline_run.reload
        expect(pipeline_run.quality_score).to eq(95)
        expect(pipeline_run.metadata['completed_steps']).to eq([ 'download', 'voiceover', 'subtitles', 'quality_check' ])
        expect(pipeline_run.metadata['approval_status']).to eq('awaiting_approval')
      end

      it 'accepts run_id string' do
        described_class.new.perform(pipeline_run.run_id, auto_publish: false)

        pipeline_run.reload
        expect(pipeline_run.metadata['approval_status']).to eq('awaiting_approval')
      end
    end

    context 'when auto_publish is true and QC recommendation is review' do
      before do
        allow(qc_service).to receive(:evaluate_quality).and_return({
          overall_score: 65,
          recommendation: 'review',
          issues: [ 'audio_volume_low' ]
        })
      end

      it 'requests approval via Telegram and does not auto-publish' do
        expect(PublishVideoJob).not_to receive(:perform_later)
        expect(telegram_service).to receive(:request_approval).with(instance_of(PipelineRun))

        described_class.new.perform(pipeline_run.id, auto_publish: true)

        pipeline_run.reload
        expect(pipeline_run.quality_score).to eq(65)
        expect(pipeline_run.metadata['approval_status']).to eq('awaiting_approval')
      end
    end

    context 'when auto_publish is true and QC recommendation is approve' do
      before do
        allow(qc_service).to receive(:evaluate_quality).and_return({
          overall_score: 92,
          recommendation: 'approve',
          issues: []
        })
      end

      it 'auto-approves and enqueues PublishVideoJob' do
        expect(telegram_service).not_to receive(:request_approval)
        expect(PublishVideoJob).to receive(:perform_later).with(pipeline_run.id, platforms: [ 'youtube', 'tiktok' ])

        described_class.new.perform(pipeline_run.id, auto_publish: true, platforms: [ 'youtube', 'tiktok' ])

        pipeline_run.reload
        expect(pipeline_run.quality_score).to eq(92)
        expect(pipeline_run.metadata['approval_status']).to eq('approved')
      end

      it 'uses existing paths when present on pipeline run' do
        existing_run = create(:pipeline_run,
                              video_project: project,
                              raw_video_path: '/existing/raw.mp4',
                              subtitles_path: '/existing/sub.srt',
                              final_video_path: '/existing/final.mp4')

        expect(arc_reel_client).to receive(:download_video).with(project.id, '/existing/raw.mp4')
        expect(subtitle_service).to receive(:generate_srt).with(anything, '/existing/sub.srt', segments: anything)
        expect(subtitle_service).to receive(:burn_subtitles).with(anything, '/existing/sub.srt', '/existing/final.mp4')

        described_class.new.perform(existing_run.id, auto_publish: true)
      end
    end

    context 'when a step fails' do
      before do
        allow(arc_reel_client).to receive(:download_video).and_raise(ArcReelClient::Error.new('Export service down'))
      end

      it 'marks the pipeline run as failed with the error message' do
        expect {
          described_class.new.perform(pipeline_run.id)
        }.to raise_error(ArcReelClient::Error, /Export service down/)

        pipeline_run.reload
        expect(pipeline_run.status).to eq('failed')
        expect(pipeline_run.error_message).to include('Export service down')
      end
    end

    context 'when video project is missing' do
      it 'raises ArgumentError and marks the run as failed' do
        allow(PipelineRun).to receive(:find).with(pipeline_run.id).and_return(pipeline_run)
        allow(pipeline_run).to receive(:video_project).and_return(nil)

        expect {
          described_class.new.perform(pipeline_run.id)
        }.to raise_error(ArgumentError, /Missing video project/)

        expect(pipeline_run).to be_failed
      end
    end
  end
end
