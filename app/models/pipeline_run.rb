class PipelineRun < ApplicationRecord
  belongs_to :video_project
  has_many :analytics_snapshots, dependent: :destroy

  enum :status, {
    pending: "pending",
    running: "running",
    completed: "completed",
    done: "done",
    failed: "failed"
  }, default: :pending

  before_validation :ensure_run_id, on: :create

  validates :run_id, presence: true, uniqueness: true
  validates :status, presence: true
  validates :quality_score, numericality: { only_integer: true, greater_than_or_equal_to: 0, less_than_or_equal_to: 100 }, allow_nil: true

  private

  def ensure_run_id
    self.run_id = "run-#{SecureRandom.hex(6)}" if run_id.blank?
  end
end
