FactoryBot.define do
  factory :channel_account do
    platform { "youtube" }
    account_name { "TechReels Daily" }
    sequence(:account_identifier) { |n| "UC_test_channel_#{n}" }
    credentials { { "token" => "sample_oauth_token" } }
    is_active { true }
  end
end
