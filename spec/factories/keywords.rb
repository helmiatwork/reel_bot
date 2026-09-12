# frozen_string_literal: true

FactoryBot.define do
  factory :keyword do
    seed { "video editing" }
    sequence(:keyword) { |n| "video editing tutorial #{n}" }
    source { "google_ads" }
    region { "ID:id" }
    avg_monthly_searches { 10_000 }
    competition { "MEDIUM" }
    competition_index { 50 }
    cpc_low_micros { 100_000 }
    cpc_high_micros { 500_000 }
    niche { "tech" }
    score { 5_000.0 }
    raw { {} }
    fetched_at { Time.current }
  end
end
