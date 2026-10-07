class VideoProject < ApplicationRecord
  has_many :pipeline_runs, dependent: :destroy

  enum :status, {
    draft: "draft",
    script_generated: "script_generated",
    rendering: "rendering",
    completed: "completed",
    failed: "failed"
  }, default: :draft

  validates :title, presence: true
  validates :status, presence: true
end
