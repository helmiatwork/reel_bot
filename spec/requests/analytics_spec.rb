# frozen_string_literal: true

require 'rails_helper'

RSpec.describe 'Analytics', :regression, type: :request do
  let(:project) { create(:video_project) }
  let(:channel1) { create(:channel_account, platform: 'youtube') }
  let(:channel2) { create(:channel_account, platform: 'tiktok', account_identifier: 'tiktok_acc_1') }
  let!(:run1) { create(:pipeline_run, video_project: project, status: :completed, quality_score: 90) }
  let!(:run2) { create(:pipeline_run, video_project: project, status: :completed, quality_score: 80) }
  let!(:run3) { create(:pipeline_run, video_project: project, status: :pending, quality_score: nil) }

  let!(:snapshot1) do
    create(:analytics_snapshot,
           pipeline_run: run1,
           channel_account: channel1,
           views: 15000,
           created_at: 2.hours.ago)
  end
  let!(:snapshot2) do
    create(:analytics_snapshot,
           pipeline_run: run2,
           channel_account: channel2,
           views: 25000,
           created_at: 1.hour.ago)
  end

  describe 'GET /analytics/data' do
    it 'returns records ordered by recorded_at descending and total count' do
      get '/analytics/data'

      expect(response).to have_http_status(:ok)
      json = JSON.parse(response.body)
      expect(json['total']).to eq(2)
      expect(json['records']).to be_an(Array)
      expect(json['records'].size).to eq(2)
      expect(json['records'].first['id']).to eq(snapshot2.id)
      expect(json['records'].last['id']).to eq(snapshot1.id)
    end

    it 'supports limit and offset pagination' do
      get '/analytics/data', params: { limit: 1, offset: 0 }

      expect(response).to have_http_status(:ok)
      json = JSON.parse(response.body)
      expect(json['total']).to eq(2)
      expect(json['records'].size).to eq(1)
      expect(json['records'].first['id']).to eq(snapshot2.id)

      get '/analytics/data', params: { limit: 1, offset: 1 }

      expect(response).to have_http_status(:ok)
      json_offset = JSON.parse(response.body)
      expect(json_offset['records'].size).to eq(1)
      expect(json_offset['records'].first['id']).to eq(snapshot1.id)
    end
  end

  describe 'GET /analytics/summary' do
    it 'returns summary metrics including total published, platform counts, and avg quality score' do
      get '/analytics/summary'

      expect(response).to have_http_status(:ok)
      json = JSON.parse(response.body)
      expect(json['total_videos_published']).to eq(2)
      expect(json['avg_quality_score']).to eq(85.0)
      expect(json['platform_counts']).to be_a(Hash)
      expect(json['platform_counts']['youtube']).to eq(1)
      expect(json['platform_counts']['tiktok']).to eq(1)
    end
  end

  describe 'GET /analytics/insights' do
    let(:fetcher_service) { instance_double(AnalyticsFetcherService) }
    let(:mock_insights) do
      {
        'summary' => 'Strong performance on short hooks',
        'top_patterns' => [ 'Fast hook' ],
        'improvements' => [ 'Increase contrast' ],
        'suggested_hooks' => [ 'Are you making this mistake?' ]
      }
    end

    before do
      allow(AnalyticsFetcherService).to receive(:new).and_return(fetcher_service)
      allow(fetcher_service).to receive(:generate_insights).and_return(mock_insights)
    end

    it 'returns generated insights with status ok' do
      get '/analytics/insights'

      expect(response).to have_http_status(:ok)
      json = JSON.parse(response.body)
      expect(json['status']).to eq('ok')
      expect(json['insights']).to eq(mock_insights)
    end
  end
end
