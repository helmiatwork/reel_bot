# frozen_string_literal: true

require 'rails_helper'

RSpec.describe 'QualityChecks', type: :request do
  let(:qc_service) { instance_double(QualityCheckService) }

  before do
    allow(QualityCheckService).to receive(:new).and_return(qc_service)
  end

  describe 'POST /quality/check' do
    let(:qc_result) do
      {
        'overall_score' => 85,
        'recommendation' => 'approve',
        'issues' => []
      }
    end

    it 'evaluates video quality and returns QC result' do
      expect(qc_service).to receive(:evaluate_quality).with(
        '/tmp/final.mp4',
        hash_including('title' => 'Sample Reel')
      ).and_return(qc_result)

      post '/quality/check',
           params: {
             video_path: '/tmp/final.mp4',
             script: { title: 'Sample Reel' },
             min_score: 70
           }.to_json,
           headers: { 'Content-Type' => 'application/json' }

      expect(response).to have_http_status(:ok)
      json = JSON.parse(response.body)
      expect(json['overall_score']).to eq(85)
      expect(json['recommendation']).to eq('approve')
      expect(json['issues']).to eq([])
    end

    it 'returns 422 if video_path or script is missing' do
      post '/quality/check',
           params: { video_path: '/tmp/final.mp4' }.to_json,
           headers: { 'Content-Type' => 'application/json' }

      expect(response).to have_http_status(:unprocessable_content)
      json = JSON.parse(response.body)
      expect(json['error']).to be_present
    end
  end
end
