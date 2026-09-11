require 'rails_helper'

RSpec.describe AnalyticsSnapshot, type: :model do
  let(:video_project) { create(:video_project) }
  let(:pipeline_run) { create(:pipeline_run, video_project: video_project) }
  let(:channel_account) { create(:channel_account) }

  describe 'validations' do
    subject do
      build(:analytics_snapshot, pipeline_run: pipeline_run, channel_account: channel_account)
    end

    it 'is valid with valid attributes' do
      expect(subject).to be_valid
    end

    it 'requires a pipeline_run' do
      subject.pipeline_run = nil
      expect(subject).not_to be_valid
      expect(subject.errors[:pipeline_run]).to be_present
    end

    it 'requires a channel_account' do
      subject.channel_account = nil
      expect(subject).not_to be_valid
      expect(subject.errors[:channel_account]).to be_present
    end

    it 'validates non-negative numericality for metrics' do
      subject.views = -1
      expect(subject).not_to be_valid
      expect(subject.errors[:views]).to be_present

      subject.views = 100
      subject.likes = -5
      expect(subject).not_to be_valid
      expect(subject.errors[:likes]).to be_present

      subject.likes = 10
      subject.comments = -2
      expect(subject).not_to be_valid
      expect(subject.errors[:comments]).to be_present

      subject.comments = 5
      subject.watch_time_minutes = -0.5
      expect(subject).not_to be_valid
      expect(subject.errors[:watch_time_minutes]).to be_present

      subject.watch_time_minutes = 12.5
      subject.ctr = -0.1
      expect(subject).not_to be_valid
      expect(subject.errors[:ctr]).to be_present
    end
  end

  describe 'associations' do
    it 'belongs to pipeline_run' do
      snapshot = create(:analytics_snapshot, pipeline_run: pipeline_run, channel_account: channel_account)
      expect(snapshot.pipeline_run).to eq(pipeline_run)
    end

    it 'belongs to channel_account' do
      snapshot = create(:analytics_snapshot, pipeline_run: pipeline_run, channel_account: channel_account)
      expect(snapshot.channel_account).to eq(channel_account)
    end
  end

  describe 'defaults and jsonb payload' do
    it 'sets sensible defaults' do
      snapshot = described_class.new
      expect(snapshot.views).to eq(0)
      expect(snapshot.likes).to eq(0)
      expect(snapshot.comments).to eq(0)
      expect(snapshot.watch_time_minutes).to eq(0.0)
      expect(snapshot.ctr).to eq(0.0)
    end

    it 'stores raw_payload' do
      payload = {
        'platform_metric_id' => 'xyz-999',
        'audience_demographics' => { 'age_18_24' => 0.45, 'age_25_34' => 0.35 }
      }
      snapshot = create(:analytics_snapshot,
                        pipeline_run: pipeline_run,
                        channel_account: channel_account,
                        raw_payload: payload)
      snapshot.reload
      expect(snapshot.raw_payload).to eq(payload)
    end
  end
end
