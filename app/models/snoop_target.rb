# frozen_string_literal: true

class SnoopTarget < ApplicationRecord
  PROHIBITED_CHARS_REGEX = /[;&|`$\n\r<>]/
  VALID_CHANNEL_REGEX = /\A(?:@[a-zA-Z0-9._-]+|UC[a-zA-Z0-9_-]{20,24}|[a-zA-Z0-9._-]+)\z/

  has_many :snoop_results,
           primary_key: :channel_id,
           foreign_key: :channel_id,
           dependent: :destroy,
           inverse_of: :snoop_target

  before_validation :normalize_channel_and_handle

  validates :channel_id, presence: true, uniqueness: { case_sensitive: false }
  validate :validate_channel_id_safety, if: -> { channel_id.present? }

  scope :recent, -> { order(created_at: :desc) }

  def self.normalize_channel_input(input)
    str = input.to_s.strip
    return { channel_id: nil, handle: nil } if str.blank?
    return { channel_id: str, handle: nil } if str.match?(PROHIBITED_CHARS_REGEX)

    if (m = str.match(%r{\A(?:https?://)?(?:www\.)?youtube\.com/@([a-zA-Z0-9._-]+)(?:[?#].*)?\z}i))
      handle = "@#{m[1]}"
      { channel_id: handle, handle: handle }
    elsif (m = str.match(%r{\A(?:https?://)?(?:www\.)?youtube\.com/channel/([a-zA-Z0-9_-]+)(?:[?#].*)?\z}i))
      { channel_id: m[1], handle: nil }
    elsif (m = str.match(%r{\A(?:https?://)?(?:www\.)?youtube\.com/c/([a-zA-Z0-9._-]+)(?:[?#].*)?\z}i))
      handle = "@#{m[1]}"
      { channel_id: handle, handle: handle }
    elsif str.start_with?("@")
      { channel_id: str, handle: str }
    else
      { channel_id: str, handle: nil }
    end
  end

  private

  def validate_channel_id_safety
    if channel_id.match?(PROHIBITED_CHARS_REGEX)
      errors.add(:channel_id, "contains prohibited characters")
    elsif !channel_id.match?(VALID_CHANNEL_REGEX)
      errors.add(:channel_id, "is invalid")
    end
  end

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
