# frozen_string_literal: true

class SnoopTarget < ApplicationRecord
  has_many :snoop_results,
           primary_key: :channel_id,
           foreign_key: :channel_id,
           dependent: :destroy,
           inverse_of: :snoop_target

  validates :channel_id, presence: true, uniqueness: { case_sensitive: false }

  before_validation :normalize_channel_and_handle

  scope :recent, -> { order(created_at: :desc) }

  def self.normalize_channel_input(input)
    str = input.to_s.strip
    return { channel_id: nil, handle: nil } if str.blank?

    if (m = str.match(%r{(?:https?://)?(?:www\.)?youtube\.com/@([a-zA-Z0-9._-]+)}i))
      handle = "@#{m[1]}"
      { channel_id: handle, handle: handle }
    elsif (m = str.match(%r{(?:https?://)?(?:www\.)?youtube\.com/channel/([a-zA-Z0-9_-]+)}i))
      { channel_id: m[1], handle: nil }
    elsif (m = str.match(%r{(?:https?://)?(?:www\.)?youtube\.com/c/([a-zA-Z0-9._-]+)}i))
      handle = "@#{m[1]}"
      { channel_id: handle, handle: handle }
    elsif str.start_with?("@")
      { channel_id: str, handle: str }
    else
      { channel_id: str, handle: nil }
    end
  end

  private

  def normalize_channel_and_handle
    if channel_id.present?
      self.channel_id = channel_id.to_s.strip
      parsed = self.class.normalize_channel_input(channel_id)
      self.channel_id = parsed[:channel_id] if parsed[:channel_id].present?
      self.handle = parsed[:handle] if handle.blank? && parsed[:handle].present?
    end

    return if handle.blank?

    self.handle = handle.to_s.strip
    self.handle = "@#{handle}" unless self.handle.start_with?("@")
  end
end
