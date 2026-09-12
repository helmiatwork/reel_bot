# frozen_string_literal: true

class SnoopResult < ApplicationRecord
  belongs_to :snoop_target,
             primary_key: :channel_id,
             foreign_key: :channel_id,
             optional: true,
             inverse_of: :snoop_results

  validates :channel_id, presence: true
  validates :video_id, presence: true

  scope :recent, -> { order(created_at: :desc) }
end
