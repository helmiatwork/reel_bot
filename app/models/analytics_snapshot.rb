class AnalyticsSnapshot < ApplicationRecord
  belongs_to :pipeline_run
  belongs_to :channel_account

  validates :views, numericality: { greater_than_or_equal_to: 0, only_integer: true }
  validates :watch_time_minutes, numericality: { greater_than_or_equal_to: 0.0 }
  validates :likes, numericality: { greater_than_or_equal_to: 0, only_integer: true }
  validates :comments, numericality: { greater_than_or_equal_to: 0, only_integer: true }
  validates :ctr, numericality: { greater_than_or_equal_to: 0.0 }
end
