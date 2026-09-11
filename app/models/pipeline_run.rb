class PipelineRun < ApplicationRecord
  belongs_to :video_project
  has_many :analytics_snapshots, dependent: :destroy

  enum :status, {
    pending: "pending",
    running: "running",
    completed: "completed",
    failed: "failed"
  }, default: :pending

  validates :run_id, presence: true, uniqueness: true
  validates :status, presence: true
  validates :quality_score, numericality: { only_integer: true, greater_than_or_equal_to: 0, less_than_or_equal_to: 100 }, allow_nil: true
end
