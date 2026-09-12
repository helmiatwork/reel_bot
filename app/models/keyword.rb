# frozen_string_literal: true

class Keyword < ApplicationRecord
  validates :keyword, presence: true
  validates :source, presence: true
  validates :region, presence: true

  scope :by_score, -> { order(score: :desc) }
  scope :by_niche, ->(niche) { where(niche: niche) if niche.present? }
  scope :by_source, ->(source) { where(source: source) if source.present? }
  scope :by_region, ->(region) { where(region: region) if region.present? }
  scope :min_volume, ->(vol) { where("avg_monthly_searches >= ?", vol) if vol.present? }

  def self.calculate_score(avg_monthly_searches:, competition_index:, niche_fit: 1.0)
    (avg_monthly_searches || 0).to_f * (1.0 - (competition_index || 0).to_f / 100.0) * (niche_fit || 1.0).to_f
  end

  def calculate_score(niche_fit: 1.0)
    self.class.calculate_score(
      avg_monthly_searches: avg_monthly_searches,
      competition_index: competition_index,
      niche_fit: niche_fit
    )
  end
end
