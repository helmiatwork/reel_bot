require 'rails_helper'

RSpec.describe ChannelAccount, type: :model do
  describe 'validations' do
    subject { build(:channel_account) }

    it 'is valid with valid attributes' do
      expect(subject).to be_valid
    end

    it 'requires a platform' do
      subject.platform = nil
      expect(subject).not_to be_valid
      expect(subject.errors[:platform]).to include("can't be blank")
    end

    it 'requires an account_name' do
      subject.account_name = nil
      expect(subject).not_to be_valid
      expect(subject.errors[:account_name]).to include("can't be blank")
    end

    it 'requires an account_identifier' do
      subject.account_identifier = nil
      expect(subject).not_to be_valid
      expect(subject.errors[:account_identifier]).to include("can't be blank")
    end

    it 'enforces uniqueness of account_identifier within platform' do
      create(:channel_account, platform: 'youtube', account_identifier: 'channel-001')
      duplicate = build(:channel_account, platform: 'youtube', account_identifier: 'channel-001')
      expect(duplicate).not_to be_valid
      expect(duplicate.errors[:account_identifier]).to include('has already been taken')

      different_platform = build(:channel_account, platform: 'tiktok', account_identifier: 'channel-001')
      expect(different_platform).to be_valid
    end

    it 'defaults is_active to true' do
      account = described_class.new
      expect(account.is_active).to be(true)
    end
  end

  describe 'platform enum / values' do
    it 'supports youtube, tiktok, and instagram platforms' do
      account = create(:channel_account, platform: 'youtube')
      expect(account.platform).to eq('youtube')

      account.platform = 'tiktok'
      expect(account).to be_valid

      account.platform = 'instagram'
      expect(account).to be_valid
    end
  end

  describe 'associations' do
    it 'has many analytics_snapshots with dependent destroy' do
      account = create(:channel_account)
      project = create(:video_project)
      run = create(:pipeline_run, video_project: project)
      snapshot = create(:analytics_snapshot, pipeline_run: run, channel_account: account)

      expect(account.analytics_snapshots).to include(snapshot)

      expect {
        account.destroy
      }.to change(AnalyticsSnapshot, :count).by(-1)
    end
  end

  describe 'jsonb credentials attribute' do
    it 'stores OAuth and token credentials securely' do
      creds = {
        'access_token' => 'mock-token-abc',
        'refresh_token' => 'mock-refresh-xyz',
        'expires_at' => 1780000000
      }
      account = create(:channel_account, credentials: creds)
      account.reload
      expect(account.credentials).to eq(creds)
    end
  end
end
