# frozen_string_literal: true

class AddUniqueIndexToSnoopResults < ActiveRecord::Migration[8.1]
  def change
    add_index :snoop_results, [ :channel_id, :video_id ], unique: true
  end
end
