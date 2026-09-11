class ChannelAccount < ApplicationRecord
  has_many :analytics_snapshots, dependent: :destroy

  validates :platform, presence: true
  validates :account_name, presence: true
  validates :account_identifier, presence: true, uniqueness: { scope: :platform }
  validates :is_active, inclusion: { in: [ true, false ] }
end
