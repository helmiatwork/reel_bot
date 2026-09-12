# frozen_string_literal: true

require 'rails_helper'

RSpec.describe ChannelAccount, type: :model, regression: true do
  describe 'constants' do
    it 'defines ACCOUNT_ROLES' do
      expect(described_class::ACCOUNT_ROLES).to eq(%w[main clip creator brand competitor])
    end

    it 'defines ACCOUNT_PLATFORMS' do
      expect(described_class::ACCOUNT_PLATFORMS).to eq(%w[youtube tiktok instagram])
    end
  end

  describe 'attribute aliases' do
    let(:account) { build(:channel_account, account_identifier: '@dailytech', account_name: 'Daily Tech', is_active: true) }

    it 'aliases handle to account_identifier' do
      expect(account.handle).to eq('@dailytech')
      account.handle = '@newhandle'
      expect(account.account_identifier).to eq('@newhandle')
    end

    it 'aliases label to account_name' do
      expect(account.label).to eq('Daily Tech')
      account.label = 'New Label'
      expect(account.account_name).to eq('New Label')
    end

    it 'aliases active to is_active' do
      expect(account.active).to be(true)
      account.active = false
      expect(account.is_active).to be(false)
    end
  end

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

    it 'validates inclusion of platform in ACCOUNT_PLATFORMS' do
      subject.platform = 'unsupported_platform'
      expect(subject).not_to be_valid
      expect(subject.errors[:platform]).to include('is not included in the list')

      %w[youtube tiktok instagram].each do |p|
        subject.platform = p
        expect(subject).to be_valid
      end
    end

    it 'validates inclusion of role in ACCOUNT_ROLES' do
      subject.role = 'invalid_role'
      expect(subject).not_to be_valid
      expect(subject.errors[:role]).to include('is not included in the list')

      %w[main clip creator brand competitor].each do |r|
        subject.role = r
        expect(subject).to be_valid
      end
    end

    it 'defaults role to main' do
      account = described_class.new
      expect(account.role).to eq('main')
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

  describe 'cookie helpers' do
    let(:account) { create(:channel_account, credentials: { 'token' => 'oauth_tok', 'cookies' => { 'session' => 'xyz123' } }) }

    describe '#cookies' do
      it 'returns the cookies stored in credentials' do
        expect(account.cookies).to eq({ 'session' => 'xyz123' })
      end

      it 'returns nil if no cookies exist' do
        account.credentials = {}
        expect(account.cookies).to be_nil
      end
    end

    describe '#update_cookies' do
      it 'updates credentials with hash cookies and persists' do
        new_cookies = { 'session_id' => 'abc999', 'secure' => 'true' }
        expect(account.update_cookies(new_cookies)).to be_truthy
        expect(account.reload.cookies).to eq(new_cookies)
        expect(account.credentials['token']).to eq('oauth_tok')
      end

      it 'updates credentials with string cookies and persists' do
        raw_cookie_str = 'session_id=abc999; path=/'
        expect(account.update_cookies(raw_cookie_str)).to be_truthy
        expect(account.reload.cookies).to eq(raw_cookie_str)
      end

      it 'updates credentials with array cookies and persists' do
        cookie_list = [ { 'name' => 'cookie1', 'value' => 'val1' } ]
        expect(account.update_cookies(cookie_list)).to be_truthy
        expect(account.reload.cookies).to eq(cookie_list)
      end
    end

    describe '#clear_cookies!' do
      it 'removes cookies from credentials and persists' do
        account.clear_cookies!
        expect(account.reload.cookies).to be_nil
        expect(account.reload.credentials.key?('cookies')).to be(false)
        expect(account.credentials['token']).to eq('oauth_tok')
      end
    end
  end

  describe '#as_json / serialization masking' do
    let(:account) do
      create(:channel_account, credentials: {
        'token' => 'secret-oauth-token',
        'access_token' => 'secret-access',
        'refresh_token' => 'secret-refresh',
        'cookies' => { 'auth_session' => 'sess_secret_val' },
        'expires_at' => 1780000000
      })
    end

    it 'excludes sensitive tokens and cookies from credentials by default' do
      json = account.as_json
      expect(json['credentials']).not_to have_key('token')
      expect(json['credentials']).not_to have_key('access_token')
      expect(json['credentials']).not_to have_key('refresh_token')
      expect(json['credentials']).not_to have_key('cookies')
      expect(json['credentials']['expires_at']).to eq(1780000000)
    end

    it 'includes sensitive tokens and cookies when explicitly requested' do
      json = account.as_json(include_sensitive: true)
      expect(json['credentials']['token']).to eq('secret-oauth-token')
      expect(json['credentials']['access_token']).to eq('secret-access')
      expect(json['credentials']['refresh_token']).to eq('secret-refresh')
      expect(json['credentials']['cookies']).to eq({ 'auth_session' => 'sess_secret_val' })
    end

    it 'excludes sensitive keys nested inside hashes and arrays' do
      nested_account = create(:channel_account, credentials: {
        'oauth' => {
          'access_token' => 'nested-secret-access',
          'client_secret' => 'nested-client-secret',
          'expires_in' => 3600
        },
        'profiles' => [
          { 'user' => 'creator_1', 'password' => 'secret_pass_1' },
          { 'user' => 'creator_2', 'token' => 'secret_token_2' }
        ],
        'session_cookies' => 'top_level_cookie',
        'public_info' => { 'username' => 'creator' }
      })

      json = nested_account.as_json
      expect(json['credentials']['oauth']).to eq({ 'expires_in' => 3600 })
      expect(json['credentials']['oauth']).not_to have_key('access_token')
      expect(json['credentials']['oauth']).not_to have_key('client_secret')
      expect(json['credentials']['profiles']).to eq([
        { 'user' => 'creator_1' },
        { 'user' => 'creator_2' }
      ])
      expect(json['credentials']).not_to have_key('session_cookies')
      expect(json['credentials']['public_info']).to eq({ 'username' => 'creator' })
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
end
