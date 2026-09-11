require 'rails_helper'

RSpec.describe PipelineRun, type: :model do
  let(:video_project) { create(:video_project) }

  describe 'validations' do
    subject { build(:pipeline_run, video_project: video_project) }

    it 'is valid with valid attributes' do
      expect(subject).to be_valid
    end

    it 'requires a run_id' do
      subject.run_id = nil
      expect(subject).not_to be_valid
      expect(subject.errors[:run_id]).to include("can't be blank")
    end

    it 'enforces run_id uniqueness' do
      create(:pipeline_run, run_id: 'unique-run-123', video_project: video_project)
      duplicate = build(:pipeline_run, run_id: 'unique-run-123', video_project: video_project)
      expect(duplicate).not_to be_valid
      expect(duplicate.errors[:run_id]).to include('has already been taken')
    end

    it 'requires a status' do
      subject.status = nil
      expect(subject).not_to be_valid
      expect(subject.errors[:status]).to include("can't be blank")
    end

    it 'validates quality_score range between 0 and 100' do
      subject.quality_score = 105
      expect(subject).not_to be_valid
      expect(subject.errors[:quality_score]).to be_present

      subject.quality_score = -5
      expect(subject).not_to be_valid
      expect(subject.errors[:quality_score]).to be_present

      subject.quality_score = 85
      expect(subject).to be_valid

      subject.quality_score = nil
      expect(subject).to be_valid
    end
  end

  describe 'status enum' do
    it 'defaults to pending' do
      run = described_class.new
      expect(run.status).to eq('pending')
    end

    it 'supports status transitions' do
      run = create(:pipeline_run, video_project: video_project)
      expect(run).to be_pending

      run.running!
      expect(run).to be_running

      run.completed!
      expect(run).to be_completed

      run.failed!
      expect(run).to be_failed
    end
  end

  describe 'associations' do
    it 'belongs to a video_project' do
      run = create(:pipeline_run, video_project: video_project)
      expect(run.video_project).to eq(video_project)
    end

    it 'has many analytics_snapshots with dependent destroy' do
      run = create(:pipeline_run, video_project: video_project)
      channel = create(:channel_account)
      snapshot = create(:analytics_snapshot, pipeline_run: run, channel_account: channel)

      expect(run.analytics_snapshots).to include(snapshot)

      expect {
        run.destroy
      }.to change(AnalyticsSnapshot, :count).by(-1)
    end
  end

  describe 'jsonb metadata attribute' do
    it 'stores execution details' do
      meta = {
        'resolution' => '1080x1920',
        'fps' => 30,
        'steps_completed' => [ 'download', 'split', 'subtitles', 'tts' ]
      }
      run = create(:pipeline_run, video_project: video_project, metadata: meta)
      run.reload
      expect(run.metadata).to eq(meta)
    end
  end
end
