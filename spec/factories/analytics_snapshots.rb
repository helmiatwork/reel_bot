FactoryBot.define do
  factory :analytics_snapshot do
    association :pipeline_run
    association :channel_account
    views { 1500 }
    watch_time_minutes { 120.5 }
    likes { 98 }
    comments { 14 }
    ctr { 0.082 }
    raw_payload { { "retention_rate" => 0.72 } }
  end
end
