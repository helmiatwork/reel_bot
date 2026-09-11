FactoryBot.define do
  factory :video_project do
    title { "Top 10 Secret AI Tools" }
    topic { "Artificial Intelligence" }
    hook { "You won't believe what this AI can do in 5 seconds." }
    script do
      {
        "intro" => "Welcome back to Tech Shorts!",
        "points" => [ "Tool 1: Claude", "Tool 2: Whisper" ],
        "outro" => "Subscribe for more!"
      }
    end
    status { :draft }
  end
end
