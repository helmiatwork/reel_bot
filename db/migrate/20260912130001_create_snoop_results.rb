# frozen_string_literal: true

class CreateSnoopResults < ActiveRecord::Migration[8.1]
  def change
    create_table :snoop_results do |t|
      t.string :channel_id, null: false
      t.string :video_id, null: false
      t.string :video_title
      t.jsonb :clips, default: [], null: false

      t.timestamps
    end

    add_index :snoop_results, :channel_id
    add_index :snoop_results, :created_at
  end
end
