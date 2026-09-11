FactoryBot.define do
  factory :pipeline_run do
    association :video_project
    sequence(:run_id) { |n| "run-#{n}-#{SecureRandom.hex(4)}" }
    status { :pending }
    raw_video_path { "/data/raw/video_001.mp4" }
    final_video_path { "/data/output/final_001.mp4" }
    subtitles_path { "/data/subtitles/sub_001.srt" }
    quality_score { 92 }
    error_message { nil }
    metadata { { "render_engine" => "ffmpeg", "codec" => "h264" } }
  end
end
