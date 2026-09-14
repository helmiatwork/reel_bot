# frozen_string_literal: true

class CreateClipFinds < ActiveRecord::Migration[8.1]
  def change
    create_table :clip_finds do |t|
      t.text :youtube_url, null: false
      t.jsonb :clips, default: [], null: false
      t.string :model, limit: 48
      t.decimal :cost_usd, precision: 10, scale: 5

      t.timestamps
    end

    add_index :clip_finds, :youtube_url
    add_index :clip_finds, :created_at
  end
end
