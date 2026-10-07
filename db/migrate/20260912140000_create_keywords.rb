# frozen_string_literal: true

class CreateKeywords < ActiveRecord::Migration[8.1]
  def change
    create_table :keywords do |t|
      t.string :seed
      t.string :keyword, null: false
      t.string :source, null: false, default: "google_ads"
      t.bigint :search_volume_min
      t.bigint :search_volume_max
      t.bigint :avg_monthly_searches
      t.string :competition
      t.integer :competition_index
      t.bigint :cpc_low_micros
      t.bigint :cpc_high_micros
      t.string :region, null: false, default: "ID:id"
      t.string :niche
      t.float :score
      t.jsonb :raw, default: {}
      t.datetime :fetched_at

      t.timestamps
    end

    add_index :keywords, [ :keyword, :region, :source ], unique: true
    add_index :keywords, :score
    add_index :keywords, :niche
    add_index :keywords, :source
    add_index :keywords, :region
    add_index :keywords, :keyword
    add_index :keywords, :fetched_at
  end
end
